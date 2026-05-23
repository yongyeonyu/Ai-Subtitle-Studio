import Foundation
import CoreML
import WhisperKit

struct LoadedAudioEntry: Sendable {
    let originalIndex: Int
    let samples: [Float]
}

struct TranscribeOutcome: @unchecked Sendable {
    let originalIndex: Int
    let result: Result<[TranscriptionResult], Swift.Error>
}

final class WhisperKitSendableBox: @unchecked Sendable {
    let kit: WhisperKit

    init(_ kit: WhisperKit) {
        self.kit = kit
    }
}

func segmentPayloads(from results: [TranscriptionResult], includeWords: Bool) -> [SegmentPayload] {
    var rows: [SegmentPayload] = []
    for result in results {
        for segment in result.segments {
            let words: [WordPayload]
            if includeWords, let segmentWords = segment.words {
                var collectedWords: [WordPayload] = []
                collectedWords.reserveCapacity(segmentWords.count)
                for item in segmentWords {
                    let word = item.word.trimmingCharacters(in: .whitespacesAndNewlines)
                    let start = Double(item.start)
                    let end = Double(item.end)
                    if !word.isEmpty && end >= start {
                        collectedWords.append(
                            WordPayload(
                                word: word,
                                start: start,
                                end: end,
                                confidence: Double(item.probability)
                            )
                        )
                    }
                }
                words = collectedWords
            } else {
                words = []
            }
            let text = segment.text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                rows.append(
                    SegmentPayload(
                        start: Double(segment.start),
                        end: max(Double(segment.start), Double(segment.end)),
                        text: text,
                        words: words
                    )
                )
            }
        }
    }
    if rows.isEmpty {
        let text = results.map { $0.text }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            rows.append(SegmentPayload(start: 0.0, end: 0.0, text: text, words: []))
        }
    }
    return rows
}

func normalizedComputeProfile(_ rawValue: String?) -> String {
    let value = (rawValue ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "-", with: "_")
    switch value {
    case "all", "full":
        return "all"
    case "gpu", "cpu_gpu", "cpuandgpu":
        return "gpu"
    case "cpu", "cpu_only", "cpuonly":
        return "cpu"
    default:
        return "ane_gpu"
    }
}

func computeOptions(for profile: String) -> ModelComputeOptions {
    switch normalizedComputeProfile(profile) {
    case "all":
        return ModelComputeOptions(
            melCompute: .all,
            audioEncoderCompute: .all,
            textDecoderCompute: .all
        )
    case "gpu":
        return ModelComputeOptions(
            melCompute: .cpuAndGPU,
            audioEncoderCompute: .cpuAndGPU,
            textDecoderCompute: .cpuAndGPU
        )
    case "cpu":
        return ModelComputeOptions(
            melCompute: .cpuOnly,
            audioEncoderCompute: .cpuOnly,
            textDecoderCompute: .cpuOnly
        )
    default:
        return ModelComputeOptions(
            melCompute: .cpuAndGPU,
            audioEncoderCompute: .cpuAndNeuralEngine,
            textDecoderCompute: .cpuAndNeuralEngine
        )
    }
}

func decodeOptions(language: String, wordTimestamps: Bool, workerCount: Int) -> DecodingOptions {
    DecodingOptions(
        verbose: false,
        task: .transcribe,
        language: language,
        wordTimestamps: wordTimestamps,
        concurrentWorkerCount: max(1, workerCount)
    )
}

func emitTranscribeResult(
    taskId: String,
    index: Int,
    result: Result<[TranscriptionResult], Swift.Error>,
    loadedModel: String,
    wordTimestamps: Bool
) {
    switch result {
    case .success(let results):
        let payload = TranscriptionPayload(
            backend: "whisperkit-persistent",
            loadedModel: loadedModel,
            segments: segmentPayloads(from: results, includeWords: wordTimestamps),
            text: results.map { $0.text }.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines),
            wordTimestamps: wordTimestamps
        )
        emit(
            WorkerResponse(
                backend: "whisperkit-persistent",
                taskId: taskId,
                index: index,
                result: payload,
                loadedModel: loadedModel,
                wordTimestamps: wordTimestamps,
                done: nil,
                error: nil,
                stage: nil
            )
        )
    case .failure(let error):
        emitError(taskId: taskId, index: index, error: error, stage: "transcribe")
    }
}

func loadAudioEntry(
    path: String,
    originalIndex: Int,
    channelMode: AudioInputConfig.ChannelMode
) -> Result<LoadedAudioEntry, Swift.Error> {
    do {
        let samples = try AudioProcessor.loadAudioAsFloatArray(fromPath: path, channelMode: channelMode)
        return .success(LoadedAudioEntry(originalIndex: originalIndex, samples: samples))
    } catch {
        return .failure(error)
    }
}

@MainActor
func transcribeStreamingRollingPool(kit: WhisperKit, request: WorkerRequest, workerCount: Int) async {
    let maxInFlight = max(1, min(workerCount, max(1, request.chunkPaths.count)))
    let language = request.language
    let wantsWordTimestamps = request.wordTimestamps
    let model = request.model
    let kitBox = WhisperKitSendableBox(kit)
    let chunkPaths = request.chunkPaths
    let channelMode = kit.audioInputConfig.channelMode
    var nextIndex = 0
    var inFlight = 0

    await withTaskGroup(of: TranscribeOutcome.self) { taskGroup in
        while inFlight < maxInFlight && nextIndex < chunkPaths.count {
            let originalIndex = nextIndex
            nextIndex += 1
            let entryResult = loadAudioEntry(path: chunkPaths[originalIndex], originalIndex: originalIndex, channelMode: channelMode)
            switch entryResult {
            case .success(let entry):
                taskGroup.addTask {
                    do {
                        let options = decodeOptions(
                            language: language,
                            wordTimestamps: wantsWordTimestamps,
                            workerCount: 1
                        )
                        let results = try await kitBox.kit.transcribe(
                            audioArray: entry.samples,
                            decodeOptions: options
                        )
                        return TranscribeOutcome(originalIndex: entry.originalIndex, result: .success(results))
                    } catch {
                        return TranscribeOutcome(originalIndex: entry.originalIndex, result: .failure(error))
                    }
                }
                inFlight += 1
            case .failure(let error):
                emitError(taskId: request.taskId, index: originalIndex, error: error, stage: "audio_load")
            }
        }

        while inFlight > 0 {
            guard let outcome = await taskGroup.next() else {
                break
            }
            inFlight -= 1
            emitTranscribeResult(
                taskId: request.taskId,
                index: outcome.originalIndex,
                result: outcome.result,
                loadedModel: model,
                wordTimestamps: wantsWordTimestamps
            )

            while inFlight < maxInFlight && nextIndex < chunkPaths.count {
                let originalIndex = nextIndex
                nextIndex += 1
                let entryResult = loadAudioEntry(path: chunkPaths[originalIndex], originalIndex: originalIndex, channelMode: channelMode)
                switch entryResult {
                case .success(let entry):
                    taskGroup.addTask {
                        do {
                            let options = decodeOptions(
                                language: language,
                                wordTimestamps: wantsWordTimestamps,
                                workerCount: 1
                            )
                            let results = try await kitBox.kit.transcribe(
                                audioArray: entry.samples,
                                decodeOptions: options
                            )
                            return TranscribeOutcome(originalIndex: entry.originalIndex, result: .success(results))
                        } catch {
                            return TranscribeOutcome(originalIndex: entry.originalIndex, result: .failure(error))
                        }
                    }
                    inFlight += 1
                case .failure(let error):
                    emitError(taskId: request.taskId, index: originalIndex, error: error, stage: "audio_load")
                }
            }
        }
    }
}
