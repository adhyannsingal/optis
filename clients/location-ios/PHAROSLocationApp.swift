import SwiftUI

@main
struct PHAROSLocationApp: App {
    var body: some Scene {
        WindowGroup { LocationView() }
    }
}

private struct LocationView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var endpoint = ""
    @State private var token = ""
    @State private var status = "Idle"
    @State private var sender: PhoneLocation?

    var body: some View {
        Form {
            TextField("Location endpoint URL", text: $endpoint)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .disabled(sender != nil)
            SecureField("Local PHAROS token", text: $token)
                .disabled(sender != nil)
            Button(sender == nil ? "Start sending location" : "Stop sending location") {
                if let sender {
                    sender.stop()
                    self.sender = nil
                    status = "Stopped"
                    return
                }
                guard let url = URL(string: endpoint.trimmingCharacters(in: .whitespacesAndNewlines)),
                      ["http", "https"].contains(url.scheme ?? ""),
                      url.host != nil, url.path == "/v1/location", !token.isEmpty else {
                    status = "Enter the /v1/location URL and token."
                    return
                }
                let sender = PhoneLocation(endpoint: url, token: token) { status = $0 }
                self.sender = sender
                status = "Waiting for a location fix."
                sender.start()
            }
            Text(status)
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background, let sender {
                sender.stop()
                self.sender = nil
                status = "Stopped when the app left the foreground."
            }
        }
        .onDisappear {
            sender?.stop()
            sender = nil
        }
    }
}
