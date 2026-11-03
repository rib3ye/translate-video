// Reads every .jpg in a folder with Apple's on-device text recognition and writes one JSON line per frame: the file
// name plus each text box found (text, confidence, and x/y/w/h as fractions of the frame, origin top left).
// Usage: ocr <frames-dir> <out.jsonl> [languages, e.g. ja-JP,en-US]
import CoreGraphics
import Foundation
import ImageIO
import Vision

struct Box: Codable { let text: String; let conf: Float; let x: Double; let y: Double; let w: Double; let h: Double }
struct FrameResult: Codable { let file: String; let boxes: [Box] }

let args = CommandLine.arguments
guard args.count >= 3 else { fatalError("usage: ocr <frames-dir> <out.jsonl> [languages]") }
let dir = args[1]
let outPath = args[2]
let wanted = args.count > 3 ? args[3].split(separator: ",").map(String.init) : ["en-US"]

let probe = VNRecognizeTextRequest()
probe.recognitionLevel = .accurate
let supported = (try? probe.supportedRecognitionLanguages()) ?? []
let languages = wanted.filter { supported.contains($0) }
for lang in wanted where !supported.contains(lang) {
    FileHandle.standardError.write("ocr: \(lang) is not supported on this Mac, skipped\n".data(using: .utf8)!)
}
guard !languages.isEmpty else { fatalError("none of \(wanted) supported; this Mac supports \(supported)") }

let files = try FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".jpg") }.sorted()
var results = [FrameResult?](repeating: nil, count: files.count)
let lock = NSLock()
var done = 0

DispatchQueue.concurrentPerform(iterations: files.count) { i in
    autoreleasepool {
        let path = dir + "/" + files[i]
        guard
            let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
            let img = CGImageSourceCreateImageAtIndex(src, 0, nil)
        else { return }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.recognitionLanguages = languages
        req.usesLanguageCorrection = true
        var boxes: [Box] = []
        do {
            try VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
            for obs in req.results ?? [] {
                guard let top = obs.topCandidates(1).first else { continue }
                let b = obs.boundingBox  // normalized, origin bottom left
                boxes.append(Box(text: top.string, conf: top.confidence, x: Double(b.minX), y: Double(1 - b.maxY),
                                 w: Double(b.width), h: Double(b.height)))
            }
        } catch {
            FileHandle.standardError.write("ocr failed on \(files[i]): \(error)\n".data(using: .utf8)!)
        }
        lock.lock()
        results[i] = FrameResult(file: files[i], boxes: boxes)
        done += 1
        if done % 500 == 0 { print("ocr \(done)/\(files.count)"); fflush(stdout) }
        lock.unlock()
    }
}

let enc = JSONEncoder()
var out = Data()
for r in results {
    guard let r = r else { continue }
    out.append(try enc.encode(r))
    out.append(0x0A)
}
try out.write(to: URL(fileURLWithPath: outPath))
print("ocr: \(results.compactMap { $0 }.count) frames, languages \(languages.joined(separator: ","))")
