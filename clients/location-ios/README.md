# Optis Location for iPhone

Open `OptisLocation.xcodeproj` in Xcode. Connect and unlock your iPhone, choose it as the run destination, then select your Apple development team in **Signing & Capabilities** and click **Run**. If Xcode reports a bundle identifier conflict, use an identifier unique to your team. Enable Developer Mode on the phone if prompted.

Run the Optis backend on a trusted local network with Valhalla configured. Choose the Mac’s Wi-Fi IPv4 address under **System Settings → Wi-Fi → Details → TCP/IP**. Launch Uvicorn with `--host MAC_IP --port 8010` using that address. Generate separate random values for `OPTIS_TOKEN` (dashboard) and `OPTIS_LOCATION_TOKEN` (phone). The iPhone token can post GPS fixes only. Use HTTPS for deployment outside the trusted development network.

1. Connect the iPhone to the same network. Open **Optis Location**, enter `http://MAC_IP:8010` and the location token, then tap **Start sending location**.
2. Allow **Local Network** and **While Using the App**, with **Precise Location** on. Keep Optis Location open. It stops sending in the background.
3. In the Optis web app, check that it says **iPhone GPS ready** and shows acceptable accuracy. Search for and select a destination.
4. With a sighted spotter, try a short route and stop the phone sender. The web app should show the lost signal and route guidance should pause. If the iPhone app restarts during a route, select the destination again to replan from a fresh fix.

The app sends latitude, longitude, accuracy, and fix timing to the backend. Optis keeps the latest fix in memory for route planning and guidance.
