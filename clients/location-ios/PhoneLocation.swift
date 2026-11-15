import AVFoundation
import CoreLocation
import Foundation

/// Sends Core Location fixes during an active foreground session.
@MainActor
final class PhoneLocation: NSObject, @preconcurrency CLLocationManagerDelegate {
    private struct Fix: Encodable {
        let seq: Int
        let lat_deg: Double
        let lon_deg: Double
        let horizontal_accuracy_m: Double
        let fix_time_utc: Date
        let age_at_send_ms: Int
    }

    private struct Announcements: Decodable {
        struct Event: Decodable {
            let event_id: String
            let text: String
            let expires_in_ms: Int
        }
        let announcement: Event?
        let camera_state: String
    }

    private let manager = CLLocationManager()
    private let endpoint: URL
    private let token: String
    private let report: (String) -> Void
    private let reportAnnouncement: (String) -> Void
    private let speech = AVSpeechSynthesizer()
    private var announcements: Task<Void, Never>?
    private var lastAnnouncement: String?
    private var seq = 0
    private var active = false
    private var sending: Task<Void, Never>?

    init(endpoint: URL, token: String, report: @escaping (String) -> Void,
         reportAnnouncement: @escaping (String) -> Void) {
        self.endpoint = endpoint
        self.token = token
        self.report = report
        self.reportAnnouncement = reportAnnouncement
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
    }

    func start() {
        active = true
        startAnnouncements()
        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            guard manager.accuracyAuthorization == .fullAccuracy else {
                report("Enable Precise Location for the route test.")
                return
            }
            manager.startUpdatingLocation()
        default:
            report("Location permission unavailable.")
        }
    }

    func stop() {
        active = false
        manager.stopUpdatingLocation()
        sending?.cancel()
        announcements?.cancel()
        announcements = nil
        speech.stopSpeaking(at: .immediate)
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func startAnnouncements() {
        guard announcements == nil else { return }
        let url = endpoint.deletingLastPathComponent().appending(path: "vision").appending(path: "announcement")
        announcements = Task { [weak self] in
            while !Task.isCancelled {
                await self?.receiveAnnouncement(url)
                try? await Task.sleep(for: .milliseconds(400))
            }
        }
    }

    private func receiveAnnouncement(_ url: URL) async {
        var request = URLRequest(url: url, timeoutInterval: 2)
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let started = ProcessInfo.processInfo.systemUptime
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard !Task.isCancelled, active else { return }
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                reportAnnouncement("Can’t receive camera announcements. Check the Optis server and token.")
                return
            }
            let reply = try JSONDecoder().decode(Announcements.self, from: data)
            guard reply.camera_state == "ready" else {
                reportAnnouncement(reply.camera_state == "disabled" ? "Optis camera is off." : "Waiting for a live camera view.")
                return
            }
            guard let event = reply.announcement,
                  event.event_id != lastAnnouncement,
                  (ProcessInfo.processInfo.systemUptime - started) * 1000 < Double(event.expires_in_ms)
            else {
                if !speech.isSpeaking { reportAnnouncement("Listening for camera announcements.") }
                return
            }
            lastAnnouncement = event.event_id
            reportAnnouncement(event.text)
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio)
            try session.setActive(true)
            speech.speak(AVSpeechUtterance(string: event.text))
        } catch {
            if active && !Task.isCancelled { reportAnnouncement("Camera announcements are unavailable.") }
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if active && manager.authorizationStatus != .notDetermined { start() }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if active { report("Location unavailable: " + error.localizedDescription) }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard active, sending == nil, let location = locations.last,
              location.horizontalAccuracy > 0 else { return }
        let age = -location.timestamp.timeIntervalSinceNow
        guard age >= 0 && age < 5 else { return }
        seq += 1
        let fix = Fix(seq: seq, lat_deg: location.coordinate.latitude,
                      lon_deg: location.coordinate.longitude,
                      horizontal_accuracy_m: location.horizontalAccuracy,
                      fix_time_utc: location.timestamp, age_at_send_ms: Int(age * 1000))
        sending = Task {
            defer { sending = nil }
            do {
                let encoder = JSONEncoder()
                // Keep subsecond precision so separate updates remain distinct.
                encoder.dateEncodingStrategy = .custom { date, encoder in
                    let formatter = ISO8601DateFormatter()
                    formatter.formatOptions.insert(.withFractionalSeconds)
                    var container = encoder.singleValueContainer()
                    try container.encode(formatter.string(from: date))
                }
                var request = URLRequest(url: endpoint, timeoutInterval: 2)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
                request.httpBody = try encoder.encode(fix)
                let (data, response) = try await URLSession.shared.data(for: request)
                guard !Task.isCancelled, active else { return }
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                if (200..<300).contains(status),
                   let reply = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    report(reply["text"] as? String ?? "Location sent.")
                } else if status == 401 {
                    report("The Optis location token was rejected.")
                } else if status == 409 {
                    report("Start a checked route in the Optis dashboard.")
                } else {
                    report("Location receiver returned HTTP \(status).")
                }
            } catch {
                if active && !Task.isCancelled { report("Can’t reach Optis. Check the URL, Wi-Fi, and Local Network permission.") }
            }
        }
    }
}
