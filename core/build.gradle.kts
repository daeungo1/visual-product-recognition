plugins {
    kotlin("multiplatform")
    id("com.android.library")
}
kotlin {
    androidTarget()
    jvm()
    jvmToolchain(17)
    sourceSets {
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}
android {
    namespace = "kr.demo.guide.core"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
