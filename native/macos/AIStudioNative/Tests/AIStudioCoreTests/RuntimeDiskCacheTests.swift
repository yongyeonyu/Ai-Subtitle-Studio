import XCTest
@testable import AIStudioCore

final class RuntimeDiskCacheTests: XCTestCase {
    func testPruneDeletesOldestFilesUntilTarget() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("runtime-cache-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let oldFile = root.appendingPathComponent("old.bin")
        let midFile = root.appendingPathComponent("mid.bin")
        let newFile = root.appendingPathComponent("new.bin")
        try Data(repeating: 1, count: 300).write(to: oldFile)
        try Data(repeating: 2, count: 300).write(to: midFile)
        try Data(repeating: 3, count: 300).write(to: newFile)
        try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 100)], ofItemAtPath: oldFile.path)
        try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 200)], ofItemAtPath: midFile.path)
        try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: 300)], ofItemAtPath: newFile.path)

        let response = RuntimeDiskCache.prune(
            payload: [
                "paths": [root.path],
                "target_total_bytes": 450,
            ]
        )

        XCTAssertEqual(response["removed_files"] as? Int, 2)
        XCTAssertEqual(response["remaining_bytes"] as? Int64, 300)
        XCTAssertFalse(FileManager.default.fileExists(atPath: oldFile.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: midFile.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: newFile.path))
    }

    func testOldestHeapUsesNameAsStableTieBreaker() {
        var entries = [
            RuntimeDiskCache.CacheEntry(mtime: 100, size: 1, path: "/tmp/b.bin", basename: "b.bin"),
            RuntimeDiskCache.CacheEntry(mtime: 100, size: 1, path: "/tmp/a.bin", basename: "a.bin"),
            RuntimeDiskCache.CacheEntry(mtime: 200, size: 1, path: "/tmp/c.bin", basename: "c.bin"),
        ]

        RuntimeDiskCache.heapifyOldestFirst(&entries)

        XCTAssertEqual(RuntimeDiskCache.popOldest(&entries)?.basename, "a.bin")
        XCTAssertEqual(RuntimeDiskCache.popOldest(&entries)?.basename, "b.bin")
        XCTAssertEqual(RuntimeDiskCache.popOldest(&entries)?.basename, "c.bin")
        XCTAssertNil(RuntimeDiskCache.popOldest(&entries))
    }
}
