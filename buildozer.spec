[app]
title = GeoApp
package.name = geoapp
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,wav,json
version = 0.1
requirements = python3,kivy,kivy_garden.mapview,plyer,requests
orientation = portrait
fullscreen = 1
p4a.branch = master

# Assets
include_files = notification.wav,saved_targets.json

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.api = 33
android.minapi = 21
android.ndk = 25b
android.arch = armeabi-v7a
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION
android.allow_backup = 1
android.hardwareAccelerated = true
android.gradle_dependencies = com.google.android.gms:play-services-location:17.0.0
