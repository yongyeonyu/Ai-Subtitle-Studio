// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AIStudioNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "AIStudioCore", targets: ["AIStudioCore"]),
        .library(name: "AIStudioMacUI", targets: ["AIStudioMacUI"]),
        .executable(name: "AIStudioNativeCLI", targets: ["AIStudioNativeCLI"])
    ],
    targets: [
        .target(name: "AIStudioCore"),
        .target(
            name: "AIStudioMacUI",
            dependencies: ["AIStudioCore"]
        ),
        .executableTarget(
            name: "AIStudioNativeCLI",
            dependencies: ["AIStudioCore"]
        ),
        .testTarget(
            name: "AIStudioCoreTests",
            dependencies: ["AIStudioCore"]
        )
    ]
)
