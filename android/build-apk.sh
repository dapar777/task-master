#!/bin/bash
set -e
cd "$(dirname "$0")"

ANDROID_SDK=/usr/lib/android-sdk
PLATFORM=$ANDROID_SDK/platforms/android-23
BUILD_TOOLS=$ANDROID_SDK/build-tools/29.0.3
ANDROID_JAR=$PLATFORM/android.jar
PACKAGE=com.taskmaster.android

echo "=== Task Master APK Build ==="
echo "Platform: $PLATFORM"
echo ""

# Clean
rm -rf gen obj classes.dex task-master.unsigned.apk task-master.apk task-master-release.apk
mkdir -p gen obj

# 1. Generate R.java
echo "1. Generating R.java..."
aapt package -f -m -J gen/ -S res/ -M AndroidManifest.xml -I "$ANDROID_JAR"

# 2. Compile Java
echo "2. Compiling Java..."
find src/ gen/ -name "*.java" > sources.txt
javac -source 1.8 -target 1.8 \
    -classpath "$ANDROID_JAR" \
    -d obj/ \
    @sources.txt
rm sources.txt

# 3. Convert to DEX
echo "3. Converting to DEX..."
/usr/lib/android-sdk/build-tools/29.0.3/dx --dex --output=classes.dex obj/

# 4. Package APK (resources only)
echo "4. Packaging resources..."
aapt package -f -M AndroidManifest.xml -S res/ -I "$ANDROID_JAR" -F task-master.unsigned.apk

# 5. Add DEX to APK
echo "5. Adding DEX..."
zip -j task-master.unsigned.apk classes.dex

# 6. Create signing keystore if not present
if [ ! -f release.jks ]; then
    echo "6. Creating keystore..."
    keytool -genkeypair -v \
        -keystore release.jks \
        -alias taskmaster \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000 \
        -dname "CN=TaskMaster, O=TaskMaster, L=Unknown, ST=Unknown, C=CZ" \
        -storepass android123 \
        -keypass android123 \
        2>/dev/null
else
    echo "6. Using existing keystore"
fi

# 7. Sign
echo "7. Signing..."
apksigner sign \
    --ks release.jks \
    --ks-pass pass:android123 \
    --key-pass pass:android123 \
    --out task-master.apk \
    task-master.unsigned.apk

# 8. Zipalign
echo "8. Aligning..."
zipalign -v -f 4 task-master.apk task-master-release.apk 2>/dev/null

rm -f task-master.unsigned.apk task-master.apk

echo ""
echo "=== BUILD SUCCESSFUL ==="
echo "Output: $(pwd)/task-master-release.apk"
ls -lh task-master-release.apk
