plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "org.lightning.app"
    compileSdk = 36  // Play target since 2026-08-31 (NF-11B1); packaging/phone_build.py TARGET_SDK

    defaultConfig {
        // CI builds the phone app (packaging/phone_build.py): a version code that grows
        // with every commit on main, so each APK installs over the last.
        val buildVersionCode = providers.gradleProperty("buildVersionCode").orNull
        applicationId = "org.lightning.app"
        manifestPlaceholders["appLabel"] = "Lightning"
        minSdk = 24
        targetSdk = 36
        versionCode = buildVersionCode?.toInt() ?: 1
        versionName = providers.gradleProperty("buildVersionName").getOrElse("0.5-m1")
        ndk {
            abiFilters += "arm64-v8a"
        }
    }

    buildTypes {
        // What ships, to GitHub (APK) and Play (AAB, bundleRelease): not debuggable, not shrunk (Chaquopy's
        // Python reaches Java by name). Unsigned here: the workflow's sign job signs it away from Gradle.
        getByName("release") {
            isDebuggable = false
            isMinifyEnabled = false
        }
    }
}

// 04b: the probe runs the shared encrypted round-trip, so it carries Lightning's own package and the committed
// dummy fixture (as package `roundtrip_fixture`, read with pkgutil). Copied at configuration, so every build
// uses the checked-out sources.
val sharedPython = layout.buildDirectory.dir("shared-python").get().asFile
sync {
    from("../../lightning") { into("lightning"); exclude("**/__pycache__/**") }
    from("../../tests/fixtures/roundtrip") { into("roundtrip_fixture") }
    into(sharedPython)
}
file("$sharedPython/roundtrip_fixture/__init__.py").writeText("")
// A build names itself where Settings shows the app version (lightning/ui/web.py reads it), so a
// screenshot says which APK took it. packaging/phone_build.py checks the APK carries exactly this name.
providers.gradleProperty("buildVersionName").orNull?.let { file("$sharedPython/lightning/build_identity.txt").writeText(it) }

chaquopy {
    sourceSets {
        // Both named: srcDir must not leave the probe's own folder out (owner's phone: the probe failed outright).
        getByName("main") { srcDir("src/main/python"); srcDir(sharedPython) }
    }
    defaultConfig {
        version = "3.13"
        extractPackages("lightning")  // migrations, seed files and the catalogue are read from disk
        pip {
            // Every package as one exact file and hash (tools/android_lock.py), and nothing from an index:
            // the four native wheels come from this repository's release android-wheels-r<run>.
            options("--no-index")
            install("-r", rootProject.file("../requirements/android.lock").absolutePath)
        }
    }
}
