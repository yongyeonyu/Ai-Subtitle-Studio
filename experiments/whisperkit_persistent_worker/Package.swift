// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WhisperKitPersistentWorker",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "WhisperKitPersistentWorker", targets: ["WhisperKitPersistentWorker"])
    ],
    dependencies: [
        .package(url: "https://github.com/argmaxinc/WhisperKit.git", branch: "main")
    ],
    targets: [
        .executableTarget(
            name: "WhisperKitPersistentWorker",
            dependencies: [
                .product(name: "WhisperKit", package: "WhisperKit")
            ]
        )
    ]
)
