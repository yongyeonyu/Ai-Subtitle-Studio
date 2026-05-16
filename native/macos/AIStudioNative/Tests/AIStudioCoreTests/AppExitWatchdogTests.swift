import XCTest
@testable import AIStudioCore

final class AppExitWatchdogTests: XCTestCase {
    func testParseOptionsClampsTimingValues() throws {
        let options = try AppExitWatchdog.parseOptions([
            "--pid", "123",
            "--delay-ms", "-10",
            "--term-grace-ms", "40",
        ])

        XCTAssertEqual(options.pid, 123)
        XCTAssertEqual(options.delayMs, 0)
        XCTAssertEqual(options.termGraceMs, 40)
    }

    func testParseOptionsRejectsMissingPID() {
        XCTAssertThrowsError(try AppExitWatchdog.parseOptions(["--delay-ms", "20"]))
    }
}
