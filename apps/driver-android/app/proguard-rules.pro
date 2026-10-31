# kotlinx.serialization: keep generated serializers for the API models.
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class com.godaily.driver.core.**$$serializer { *; }
-keepclassmembers class com.godaily.driver.core.** {
    *** Companion;
}
-keepclasseswithmembers class com.godaily.driver.core.** {
    kotlinx.serialization.KSerializer serializer(...);
}
