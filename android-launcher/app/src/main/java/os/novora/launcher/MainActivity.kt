package os.novora.launcher

import android.content.Context
import android.content.Intent
import android.content.pm.LauncherApps
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.graphics.drawable.toBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val COLUMNS = 4
private const val ROWS = 6
private const val DOCK_SIZE = 4

data class AppEntry(val label: String, val packageName: String, val icon: ImageBitmap)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { LauncherScreen() }
    }
}

/** Lee las apps con icono de lanzador y las ordena alfabéticamente. */
private suspend fun loadApps(context: Context): List<AppEntry> = withContext(Dispatchers.IO) {
    val launcherApps = context.getSystemService(LauncherApps::class.java)
    launcherApps.getActivityList(null, Process.myUserHandle())
        .filter { it.applicationInfo.packageName != context.packageName }
        .map {
            val bmp: Bitmap = it.getBadgedIcon(0).toBitmap(144, 144)
            AppEntry(it.label.toString(), it.applicationInfo.packageName, bmp.asImageBitmap())
        }
        .distinctBy { it.packageName }
        .sortedBy { it.label.lowercase() }
}

private fun launch(context: Context, app: AppEntry) {
    context.packageManager.getLaunchIntentForPackage(app.packageName)?.let {
        context.startActivity(it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

/** El Dock se guarda como lista de paquetes en SharedPreferences. */
private class DockStore(context: Context) {
    private val prefs = context.getSharedPreferences("dock", Context.MODE_PRIVATE)
    fun load(): List<String> = prefs.getString("apps", null)?.split(",")?.filter { it.isNotBlank() } ?: emptyList()
    fun save(apps: List<String>) = prefs.edit().putString("apps", apps.joinToString(",")).apply()
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun LauncherScreen() {
    val context = LocalContext.current
    val dockStore = remember { DockStore(context) }
    var apps by remember { mutableStateOf<List<AppEntry>>(emptyList()) }
    var dock by remember { mutableStateOf(dockStore.load()) }
    var searching by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        apps = loadApps(context)
        // Primera ejecución: rellena el Dock con las primeras apps, como un iPhone nuevo.
        if (dock.isEmpty()) {
            dock = apps.take(DOCK_SIZE).map { it.packageName }
            dockStore.save(dock)
        }
    }

    fun toggleDock(app: AppEntry) {
        dock = if (app.packageName in dock) dock - app.packageName
        else (dock + app.packageName).takeLast(DOCK_SIZE)
        dockStore.save(dock)
    }

    val dockApps = dock.mapNotNull { pkg -> apps.find { it.packageName == pkg } }
    val pageApps = apps.filter { it.packageName !in dock }.chunked(COLUMNS * ROWS)
    val pagerState = rememberPagerState { pageApps.size.coerceAtLeast(1) }

    BackHandler(enabled = searching) { searching = false }

    Box(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            // Deslizar hacia abajo abre la búsqueda (Spotlight).
            .pointerInput(Unit) {
                var total = 0f
                detectVerticalDragGestures(
                    onDragStart = { total = 0f },
                    onDragEnd = { if (total > 150f) searching = true },
                ) { _, dy -> total += dy }
            }
    ) {
        Column(Modifier.fillMaxSize()) {
            HorizontalPager(state = pagerState, modifier = Modifier.weight(1f)) { page ->
                AppGrid(pageApps.getOrElse(page) { emptyList() }, dock, ::toggleDock)
            }
            PageDots(pagerState.pageCount, pagerState.currentPage)
            Dock(dockApps, dock, ::toggleDock)
        }

        AnimatedVisibility(searching, enter = fadeIn(), exit = fadeOut()) {
            SearchOverlay(apps) { searching = false }
        }
    }
}

@Composable
private fun AppGrid(apps: List<AppEntry>, dock: List<String>, onToggleDock: (AppEntry) -> Unit) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(COLUMNS),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(22.dp),
        userScrollEnabled = false,
        modifier = Modifier.fillMaxSize(),
    ) {
        items(apps, key = { it.packageName }) { app ->
            AppIcon(app, inDock = app.packageName in dock, showLabel = true, onToggleDock = onToggleDock)
        }
    }
}

@Composable
private fun Dock(apps: List<AppEntry>, dock: List<String>, onToggleDock: (AppEntry) -> Unit) {
    Row(
        Modifier
            .padding(horizontal = 12.dp, vertical = 10.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(32.dp))
            // Vidrio esmerilado aproximado (el desenfoque real requiere API 31+).
            .background(Color.White.copy(alpha = 0.28f))
            .padding(vertical = 14.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        apps.forEach { AppIcon(it, inDock = it.packageName in dock, showLabel = false, onToggleDock = onToggleDock) }
    }
}

@Composable
private fun PageDots(count: Int, current: Int) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.Center,
    ) {
        repeat(count) { i ->
            Box(
                Modifier
                    .padding(horizontal = 4.dp)
                    .size(7.dp)
                    .clip(RoundedCornerShape(50))
                    .background(Color.White.copy(alpha = if (i == current) 0.95f else 0.4f))
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun AppIcon(app: AppEntry, inDock: Boolean, showLabel: Boolean, onToggleDock: (AppEntry) -> Unit) {
    val context = LocalContext.current
    var menu by remember { mutableStateOf(false) }

    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(76.dp)) {
        Box {
            Image(
                bitmap = app.icon,
                contentDescription = app.label,
                modifier = Modifier
                    .size(60.dp)
                    .clip(RoundedCornerShape(14.dp)) // esquinas tipo "squircle" de iOS
                    .combinedClickable(onClick = { launch(context, app) }, onLongClick = { menu = true }),
            )
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(
                    text = { Text(if (inDock) "Quitar del Dock" else "Añadir al Dock") },
                    onClick = { menu = false; onToggleDock(app) },
                )
                DropdownMenuItem(text = { Text("Información de la app") }, onClick = {
                    menu = false
                    context.startActivity(
                        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${app.packageName}"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                })
                DropdownMenuItem(text = { Text("Eliminar app", color = Color(0xFFFF3B30)) }, onClick = {
                    menu = false
                    context.startActivity(
                        Intent(Intent.ACTION_DELETE, Uri.parse("package:${app.packageName}"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                })
            }
        }
        if (showLabel) {
            Text(
                app.label,
                color = Color.White,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 5.dp),
            )
        }
    }
}

@Composable
private fun SearchOverlay(apps: List<AppEntry>, onClose: () -> Unit) {
    val context = LocalContext.current
    var query by remember { mutableStateOf("") }
    val focus = remember { FocusRequester() }
    val results = if (query.isBlank()) emptyList()
    else apps.filter { it.label.contains(query, ignoreCase = true) }

    LaunchedEffect(Unit) { focus.requestFocus() }

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.6f))
            .padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            BasicTextField(
                value = query,
                onValueChange = { query = it },
                singleLine = true,
                textStyle = TextStyle(color = Color.White, fontSize = 17.sp),
                cursorBrush = SolidColor(Color.White),
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color.White.copy(alpha = 0.18f))
                    .padding(horizontal = 14.dp, vertical = 10.dp)
                    .focusRequester(focus),
                decorationBox = { inner ->
                    if (query.isEmpty()) Text("Buscar", color = Color.White.copy(alpha = 0.6f), fontSize = 17.sp)
                    inner()
                },
            )
            Text(
                "Cancelar",
                color = Color(0xFF0A84FF),
                fontSize = 17.sp,
                modifier = Modifier.padding(start = 12.dp).clickable(onClick = onClose),
            )
        }
        Spacer(Modifier.height(16.dp))
        results.forEach { app ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { launch(context, app); onClose() }
                    .padding(vertical = 8.dp),
            ) {
                Image(app.icon, app.label, Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)))
                Text(app.label, color = Color.White, fontSize = 16.sp, modifier = Modifier.padding(start = 12.dp))
            }
        }
    }
}
