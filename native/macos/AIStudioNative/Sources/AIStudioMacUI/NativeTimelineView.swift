import AIStudioCore
import AppKit
import SwiftUI

@available(macOS 14.0, *)
public struct NativeTimelineSegment: Identifiable, Equatable, Sendable {
    public var id: String
    public var line: Int?
    public var start: Double
    public var end: Double
    public var lane: Int
    public var isGap: Bool
    public var isPending: Bool
    public var sttPreviewSource: String?

    public init(
        id: String,
        line: Int? = nil,
        start: Double,
        end: Double,
        lane: Int = 0,
        isGap: Bool = false,
        isPending: Bool = false,
        sttPreviewSource: String? = nil
    ) {
        self.id = id
        self.line = line
        self.start = start
        self.end = end
        self.lane = lane
        self.isGap = isGap
        self.isPending = isPending
        self.sttPreviewSource = sttPreviewSource
    }
}

@available(macOS 14.0, *)
public struct NativeTimelineWaveformColumn: Equatable, Sendable {
    public var height: Int
    public var speech: Bool

    public init(height: Int, speech: Bool = false) {
        self.height = height
        self.speech = speech
    }
}

@available(macOS 14.0, *)
public struct NativeTimelineState: Equatable, Sendable {
    public var segments: [NativeTimelineSegment]
    public var waveformColumns: [NativeTimelineWaveformColumn]
    public var playheadSec: Double
    public var viewStart: Double
    public var viewEnd: Double

    public init(
        segments: [NativeTimelineSegment] = [],
        waveformColumns: [NativeTimelineWaveformColumn] = [],
        playheadSec: Double = 0,
        viewStart: Double = 0,
        viewEnd: Double = 1
    ) {
        self.segments = segments
        self.waveformColumns = waveformColumns
        self.playheadSec = playheadSec
        self.viewStart = viewStart
        self.viewEnd = viewEnd
    }
}

@available(macOS 14.0, *)
public struct NativeTimelineView: View {
    public var state: NativeTimelineState

    public init(state: NativeTimelineState) {
        self.state = state
    }

    public var body: some View {
        ZStack {
            Canvas(opaque: true, colorMode: .linear, rendersAsynchronously: true) { context, size in
                drawBackground(context: context, size: size)
                drawWaveform(context: context, size: size)
                drawSegments(context: context, size: size)
            }
            .drawingGroup(opaque: true, colorMode: .linear)

            NativeTimelinePlayheadOverlay(
                playheadSec: state.playheadSec,
                viewStart: state.viewStart,
                viewEnd: state.viewEnd
            )
        }
    }

    private func drawBackground(context: GraphicsContext, size: CGSize) {
        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(Color(red: 0.08, green: 0.11, blue: 0.12)))
        let ruler = CGRect(x: 0, y: 0, width: size.width, height: 24)
        context.fill(Path(ruler), with: .color(Color(red: 0.14, green: 0.13, blue: 0.11)))
    }

    private func drawWaveform(context: GraphicsContext, size: CGSize) {
        guard !state.waveformColumns.isEmpty else { return }
        let yBase = max(34, size.height * 0.42)
        let maxHeight = max(1, size.height * 0.26)
        let count = state.waveformColumns.count
        let columnWidth = max(1.0, size.width / CGFloat(max(1, count)))

        for (index, column) in state.waveformColumns.enumerated() {
            let x = CGFloat(index) * columnWidth
            let normalized = min(1.0, max(0.04, CGFloat(column.height) / 14.0))
            let height = normalized * maxHeight
            let rect = CGRect(
                x: floor(x),
                y: yBase - height * 0.5,
                width: max(1.0, ceil(columnWidth)),
                height: max(1.0, height)
            )
            let color = column.speech
                ? Color(red: 0.31, green: 0.96, blue: 0.93).opacity(0.92)
                : Color(red: 0.20, green: 0.50, blue: 0.50).opacity(0.56)
            context.fill(Path(rect), with: .color(color))
        }
    }

    private func drawSegments(context: GraphicsContext, size: CGSize) {
        let request = TimelineSegmentLayoutRequest(
            segments: state.segments.map {
                TimelineSegmentLayoutInput(
                    id: $0.id,
                    line: $0.line,
                    start: $0.start,
                    end: $0.end,
                    lane: $0.lane,
                    isGap: $0.isGap,
                    isPending: $0.isPending,
                    sttPreviewSource: $0.sttPreviewSource
                )
            },
            viewStart: state.viewStart,
            viewEnd: state.viewEnd,
            width: Int(size.width.rounded(.down)),
            top: Int(max(54, size.height - 34)),
            rowHeight: 22,
            laneGap: 2,
            minWidth: 2,
            padSec: 0.2,
            playheadSec: state.playheadSec
        )
        let layouts = TimelineLayout.segmentLayouts(request).layouts
        for layout in layouts {
            let rect = CGRect(
                x: CGFloat(layout.clippedX),
                y: CGFloat(layout.y),
                width: CGFloat(layout.clippedWidth),
                height: CGFloat(layout.height)
            )
            let style = segmentStyle(for: layout)
            let fill = (layout.isActive && !layout.isPending) ? Color.white.opacity(0.92) : style.fill
            context.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(fill))
            context.stroke(Path(roundedRect: rect, cornerRadius: 2), with: .color(style.border), lineWidth: 1)
            if let badge = style.badge, rect.width >= 48, rect.height >= 18 {
                drawSourceBadge(badge, context: context, segmentRect: rect, fill: style.badgeFill, border: style.badgeBorder)
            }
        }
    }

    private func segmentStyle(for layout: TimelineSegmentLayout) -> (
        fill: Color,
        border: Color,
        badge: String?,
        badgeFill: Color,
        badgeBorder: Color
    ) {
        let source = layout.sttPreviewSource ?? ""
        if layout.isPending && source == "STT1" {
            return (
                Color(red: 0.10, green: 0.32, blue: 0.18).opacity(0.90),
                Color(red: 0.20, green: 0.78, blue: 0.35).opacity(0.95),
                "STT1",
                Color(red: 0.05, green: 0.23, blue: 0.15).opacity(0.95),
                Color(red: 0.20, green: 0.78, blue: 0.35).opacity(0.95)
            )
        }
        if layout.isPending && source == "STT2" {
            return (
                Color(red: 0.10, green: 0.24, blue: 0.32).opacity(0.90),
                Color(red: 0.39, green: 0.82, blue: 1.0).opacity(0.95),
                "STT2",
                Color(red: 0.06, green: 0.18, blue: 0.26).opacity(0.95),
                Color(red: 0.39, green: 0.82, blue: 1.0).opacity(0.95)
            )
        }
        if layout.isPending {
            return (
                Color(red: 1.0, green: 0.27, blue: 0.23).opacity(0.82),
                Color.white.opacity(0.30),
                nil,
                Color.clear,
                Color.clear
            )
        }
        return (
            Color.white.opacity(0.74),
            Color.white.opacity(0.30),
            nil,
            Color.clear,
            Color.clear
        )
    }

    private func drawSourceBadge(
        _ label: String,
        context: GraphicsContext,
        segmentRect: CGRect,
        fill: Color,
        border: Color
    ) {
        let width = min(CGFloat(34), max(CGFloat(28), segmentRect.width - 8))
        let height = min(CGFloat(16), max(CGFloat(12), segmentRect.height - 8))
        let rect = CGRect(
            x: segmentRect.minX + 5,
            y: segmentRect.minY + 4,
            width: width,
            height: height
        )
        context.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(fill))
        context.stroke(Path(roundedRect: rect, cornerRadius: 2), with: .color(border), lineWidth: 1)
        context.draw(
            Text(label)
                .font(.system(size: 8, weight: .bold, design: .default))
                .foregroundStyle(Color.white),
            in: rect
        )
    }

}

@available(macOS 14.0, *)
public struct NativeTimelinePlayheadOverlay: NSViewRepresentable {
    public var playheadSec: Double
    public var viewStart: Double
    public var viewEnd: Double

    public init(playheadSec: Double, viewStart: Double, viewEnd: Double) {
        self.playheadSec = playheadSec
        self.viewStart = viewStart
        self.viewEnd = viewEnd
    }

    public func makeNSView(context: Context) -> NativeTimelinePlayheadView {
        NativeTimelinePlayheadView()
    }

    public func updateNSView(_ nsView: NativeTimelinePlayheadView, context: Context) {
        nsView.setPlayhead(playheadSec, viewStart: viewStart, viewEnd: viewEnd)
    }
}

@available(macOS 14.0, *)
public final class NativeTimelinePlayheadView: NSView {
    private let lineLayer = CALayer()
    private let handleLayer = CALayer()
    private var playheadSec: Double = 0
    private var viewStart: Double = 0
    private var viewEnd: Double = 1

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setupLayers()
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupLayers()
    }

    public override var isFlipped: Bool { true }

    public func setPlayhead(_ sec: Double, viewStart: Double, viewEnd: Double) {
        self.playheadSec = sec
        self.viewStart = viewStart
        self.viewEnd = viewEnd
        layoutPlayhead(disableAnimation: false)
    }

    public override func layout() {
        super.layout()
        layoutPlayhead(disableAnimation: true)
    }

    private func setupLayers() {
        wantsLayer = true
        layer?.masksToBounds = true
        lineLayer.backgroundColor = NSColor.systemRed.cgColor
        handleLayer.backgroundColor = NSColor.systemYellow.cgColor
        handleLayer.cornerRadius = 5
        layer?.addSublayer(lineLayer)
        layer?.addSublayer(handleLayer)
    }

    private func layoutPlayhead(disableAnimation: Bool) {
        guard bounds.width > 0, bounds.height > 0 else { return }
        let dirty = TimelineLayout.playheadDirtyRect(TimelinePlayheadDirtyRequest(
            oldSec: nil,
            newSec: playheadSec,
            viewStart: viewStart,
            viewEnd: viewEnd,
            width: Int(bounds.width.rounded(.down)),
            height: Int(bounds.height.rounded(.down)),
            extraPx: 12
        ))
        let x = CGFloat(dirty.x)
        let changes = {
            self.lineLayer.frame = CGRect(x: x - 1, y: 0, width: 2, height: self.bounds.height)
            self.handleLayer.frame = CGRect(x: x - 5, y: 2, width: 10, height: 10)
        }
        if disableAnimation {
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            changes()
            CATransaction.commit()
        } else {
            changes()
        }
    }
}
