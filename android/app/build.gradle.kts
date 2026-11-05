plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "org.lightning.app"
    compileSdk = 35

    defaultConfig {
        // CI builds the test app (packaging/phone_build.py): its own ID and label, and a version code that grows
        // with every commit on main, so each test APK installs over the last. org.lightning.app stays for Play.
        val testVersionCode = providers.gradleProperty("testVersionCode").orNull
        applicationId = if (testVersionCode != null) "org.lightning.app.test" else "org.lightning.app"
        manifestPlaceholders["appLabel"] = "Lightning"
        minSdk = 24
        targetSdk = 35
        versionCode = testVersionCode?.toInt() ?: 1
        versionName = providers.gradleProperty("testVersionName").getOrElse("0.5-m1")
        ndk {
            abiFilters += "arm64-v8a"
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
// A test build names itself where Settings shows the app version (lightning/ui/web.py reads it), so a
// screenshot says which APK took it. packaging/phone_build.py checks the APK carries exactly this name.
providers.gradleProperty("testVersionName").orNull?.let { file("$sharedPython/lightning/build_identity.txt").writeText(it) }

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
