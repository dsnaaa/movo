plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.dsnaaa.movo"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.dsnaaa.movo"
        minSdk = 26
        targetSdk = 35
        versionCode = 25
        versionName = "2.0.0"

        // 默认打开的页面。可以在 App 里用 adb 覆盖（见 README），不用重新打包
        buildConfigField("String", "DEFAULT_URL", "\"https://192.168.31.12:5888/touchpad\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // 侧载自用：先不签名，需要时用 keytool 生成 keystore 后在这里配 signingConfigs
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.12.1")
}
