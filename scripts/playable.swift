// Asks macOS itself whether it can play a video file, the way QuickTime and Finder previews would.
// Usage: playable <file>   Exits 0 when playable.
import AVFoundation

let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let kinds = asset.tracks.map { $0.mediaType.rawValue }.joined(separator: ",")
print("playable: \(asset.isPlayable); tracks: \(kinds); seconds: \(String(format: "%.2f", CMTimeGetSeconds(asset.duration)))")
exit(asset.isPlayable ? 0 : 1)
