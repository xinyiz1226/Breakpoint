// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Breakpoint",
    defaultLocalization: "en",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "BreakpointEngine", targets: ["BreakpointEngine"]),
    ],
    targets: [
        .target(
            name: "BreakpointEngine",
            path: "Breakpoint/Engine"
        ),
        .testTarget(
            name: "BreakpointTests",
            dependencies: ["BreakpointEngine"],
            path: "BreakpointTests"
        ),
    ]
)
