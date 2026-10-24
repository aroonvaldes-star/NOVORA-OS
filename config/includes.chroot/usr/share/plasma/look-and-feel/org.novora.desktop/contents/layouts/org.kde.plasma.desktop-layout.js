// NOVORA OS — disposición del escritorio (Plasma 6, API de scripting).
// Barra superior: lanzador NOVORA, menú global de la app activa, bandeja y reloj.
// Dock inferior: flotante, centrado, ajustado a su contenido; se aparta de las ventanas.

var barra = new Panel;
barra.location = "top";
barra.height = Math.round(gridUnit * 1.6);
barra.floating = false;
barra.lengthMode = "fill";
barra.hiding = "none";

var launcher = barra.addWidget("org.kde.plasma.kickoff");
launcher.currentConfigGroup = ["General"];
launcher.writeConfig("icon", "novora-logo");
barra.addWidget("org.kde.plasma.appmenu");        // menú global
barra.addWidget("org.kde.plasma.panelspacer");
barra.addWidget("org.kde.plasma.systemtray");
var clock = barra.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", "true");
clock.writeConfig("dateDisplayFormat", "BesideTime");

var dock = new Panel;
dock.location = "bottom";
dock.height = Math.round(gridUnit * 3.2);
dock.floating = true;
dock.lengthMode = "fit";
dock.alignment = "center";
dock.hiding = "dodgewindows";

var tasks = dock.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:org.kde.dolphin.desktop",
    "applications:org.kde.konsole.desktop",
    "applications:org.kde.kate.desktop",
    "applications:novora-atlas.desktop",
    "applications:org.kde.discover.desktop",
    "applications:systemsettings.desktop"
]);
tasks.writeConfig("showOnlyCurrentDesktop", "false");
dock.addWidget("org.kde.plasma.trash");

// Fondo NOVORA en todos los escritorios (con variante oscura automática).
var desks = desktops();
for (var i = 0; i < desks.length; ++i) {
    desks[i].wallpaperPlugin = "org.kde.image";
    desks[i].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desks[i].writeConfig("Image", "file:///usr/share/wallpapers/Novora/");
}
