import CoreGraphics
import Foundation

public enum InputActivity {
    public static func snapshot(payload: [String: Any] = [:]) -> [String: Any] {
        let threshold = doubleSetting(payload["recent_threshold_sec"], defaultValue: 0.25)
        let sourceState = CGEventSourceStateID.combinedSessionState
        let eventTypes: [(String, CGEventType)] = [
            ("mouse_moved", .mouseMoved),
            ("left_mouse_down", .leftMouseDown),
            ("left_mouse_up", .leftMouseUp),
            ("right_mouse_down", .rightMouseDown),
            ("right_mouse_up", .rightMouseUp),
            ("other_mouse_down", .otherMouseDown),
            ("other_mouse_up", .otherMouseUp),
            ("left_mouse_dragged", .leftMouseDragged),
            ("right_mouse_dragged", .rightMouseDragged),
            ("other_mouse_dragged", .otherMouseDragged),
            ("scroll_wheel", .scrollWheel),
            ("key_down", .keyDown),
            ("key_up", .keyUp),
            ("flags_changed", .flagsChanged)
        ]

        var ages: [String: Double] = [:]
        var bestName = ""
        var bestAge = Double.greatestFiniteMagnitude
        for (name, eventType) in eventTypes {
            let age = CGEventSource.secondsSinceLastEventType(sourceState, eventType: eventType)
            if age.isFinite && age >= 0 {
                let rounded = round4(age)
                ages[name] = rounded
                if age < bestAge {
                    bestAge = age
                    bestName = name
                }
            }
        }

        let hasEvent = bestAge.isFinite && bestAge < Double.greatestFiniteMagnitude
        let ageForOutput = hasEvent ? round4(bestAge) : -1.0
        return [
            "source": "swift_cgevent_source",
            "ok": hasEvent,
            "recent": hasEvent && bestAge <= max(0.0, threshold),
            "event_type": bestName,
            "age_sec": ageForOutput,
            "threshold_sec": round4(threshold),
            "events": ages
        ]
    }

    private static func doubleSetting(_ value: Any?, defaultValue: Double) -> Double {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let text = value as? String, let parsed = Double(text) {
            return parsed
        }
        if let value = value as? Double {
            return value
        }
        if let value = value as? Float {
            return Double(value)
        }
        if let value = value as? Int {
            return Double(value)
        }
        return defaultValue
    }

    private static func round4(_ value: Double) -> Double {
        if !value.isFinite {
            return value
        }
        return (value * 10_000.0).rounded() / 10_000.0
    }
}
