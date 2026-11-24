import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val apiBaseUrl: String = providers.gradleProperty("goDailyApiBaseUrl").get()

// Release identity (U42), set per build: -PgoDailyVersionCode=12 -PgoDailyVersionName=1.2.0
// versionCode must grow with every release; the server's minimum/recommended
// version policy (U44) compares against it.
val appVersionCode: Int = providers.gradleProperty("goDailyVersionCode").orNull?.toInt() ?: 1
val appVersionName: String = providers.gradleProperty("goDailyVersionName").orNull ?: "0.1.0"
// "production" (default) or "staging": staging builds install side by side
// (own application id) and show their environment on the home screen.
val appEnvironment: String = providers.gradleProperty("goDailyEnvironment").orNull ?: "production"
check(appEnvironment in setOf("production", "staging")) { "goDailyEnvironment must be production or staging" }

// Release signing comes from an untracked keystore.properties (never committed).
val signing = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

android {
    namespace = "com.godaily.driver"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.godaily.driver"
        minSdk = 26
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersionName
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
        buildConfigField("String", "ENVIRONMENT", "\"$appEnvironment\"")
        if (appEnvironment == "staging") {
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
        }
    }

    signingConfigs {
        if (signing.isNotEmpty()) {
            create("release") {
                storeFile = rootProject.file(signing.getProperty("storeFile"))
                storePassword = signing.getProperty("storePassword")
                keyAlias = signing.getProperty("keyAlias")
                keyPassword = signing.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfigs.findByName("release")?.let { signingConfig = it }
            check(apiBaseUrl.startsWith("https://") || !gradle.startParameter.taskNames.any {
                it.contains("Release", ignoreCase = true)
            }) { "Release builds require an https goDailyApiBaseUrl" }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    androidResources {
        localeFilters += listOf("ar")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("com.godaily.driver:core")
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.service)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.work.runtime.ktx)
    implementation(libs.play.services.location)
    debugImplementation(libs.compose.ui.tooling)
}
