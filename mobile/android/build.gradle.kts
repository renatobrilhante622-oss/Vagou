import com.android.build.api.dsl.ApplicationExtension
import com.android.build.api.dsl.LibraryExtension
import com.android.build.api.variant.LibraryAndroidComponentsExtension

plugins {
    id("com.android.application") apply false
    id("com.android.library") apply false
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val sharedBuildDirectory = rootProject.layout.buildDirectory.dir("../../build").get()
rootProject.layout.buildDirectory.value(sharedBuildDirectory)

subprojects {
    layout.buildDirectory.value(sharedBuildDirectory.dir(name))
    evaluationDependsOn(":app")

    // Flutter plugins live outside android/. Finalize their Android DSL so a
    // plugin's own build script cannot subsequently restore an older SDK.
    pluginManager.withPlugin("com.android.library") {
        extensions.configure<LibraryAndroidComponentsExtension> {
            finalizeDsl { library ->
                library.compileSdk = 36
            }
        }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}

tasks.register("verifyAndroidSdkConfiguration") {
    doLast {
        val app = project(":app").extensions.getByType<ApplicationExtension>()
        check(app.compileSdk == 36) { "App compileSdk must be 36" }
        check(app.defaultConfig.targetSdk == 36) { "App targetSdk must be 36" }
        check(app.defaultConfig.minSdk == 24) { "App minSdk must be 24" }
        allprojects.forEach { module ->
            module.extensions.findByType<LibraryExtension>()?.let { library ->
                check(library.compileSdk == 36) {
                    "${module.path} must compile against Android API 36"
                }
            }
        }
    }
}
