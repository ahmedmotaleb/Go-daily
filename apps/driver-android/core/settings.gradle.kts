// Standalone build: pure Kotlin/JVM, resolvable without Google Maven so it
// can be built and tested anywhere (CI included). The Android app consumes
// it through `includeBuild("core")`.
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}

rootProject.name = "core"
