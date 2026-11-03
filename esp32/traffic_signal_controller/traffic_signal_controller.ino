/*
 * ============================================================================
 * 🚦 ADAPTIVE TRAFFIC SIGNAL CONTROLLER - ESP32 FIRMWARE
 * Target Board: DOIT ESP32 DEVKIT V1
 * ============================================================================
 * 
 * Hardware Pin Mapping:
 * NORTH: Red = GPIO 13, Yellow = GPIO 12, Green = GPIO 14
 * SOUTH: Red = GPIO 27, Yellow = GPIO 26, Green = GPIO 25
 * EAST:  Red = GPIO 33, Yellow = GPIO 32, Green = GPIO 23
 * WEST:  Red = GPIO 22, Yellow = GPIO 21, Green = GPIO 19
 * 
 * HTTP Endpoints:
 * - GET /                                -> Status string & HTML Dashboard
 * - GET /status                         -> JSON status of all 4 lanes
 * - GET /signal?lane=North&signal=GREEN -> Set single lane (others remain unchanged)
 * - GET /traffic?north=RED&south=GREEN&east=RED&west=RED -> Atomic 4-lane update
 * - GET /reset                          -> Safe state: ALL RED
 * - GET /all_off                        -> Turns all 12 LEDs OFF
 * ============================================================================
 */

#include <WiFi.h>
#include <WebServer.h>

// ============================================================================
// WI-FI CONFIGURATION
// Replace with your local 2.4GHz Wi-Fi credentials before flashing
// ============================================================================
const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// Web server running on standard HTTP port 80
WebServer server(80);

// ============================================================================
// GPIO PIN DEFINITIONS
// ============================================================================
// North Lane
const int PIN_NORTH_RED    = 13;
const int PIN_NORTH_YELLOW = 12;
const int PIN_NORTH_GREEN  = 14;

// South Lane
const int PIN_SOUTH_RED    = 27;
const int PIN_SOUTH_YELLOW = 26;
const int PIN_SOUTH_GREEN  = 25;

// East Lane
const int PIN_EAST_RED     = 33;
const int PIN_EAST_YELLOW  = 32;
const int PIN_EAST_GREEN   = 23;

// West Lane
const int PIN_WEST_RED     = 22;
const int PIN_WEST_YELLOW  = 21;
const int PIN_WEST_GREEN   = 19;

// State tracking for each lane ("RED", "YELLOW", "GREEN", "OFF")
String stateNorth = "RED";
String stateSouth = "RED";
String stateEast  = "RED";
String stateWest  = "RED";

// ============================================================================
// HARDWARE CONTROL FUNCTIONS
// ============================================================================

void applyLaneSignal(const String& laneName, const String& signal) {
  int pinRed = -1, pinYellow = -1, pinGreen = -1;
  String* targetState = nullptr;

  if (laneName.equalsIgnoreCase("North")) {
    pinRed    = PIN_NORTH_RED;
    pinYellow = PIN_NORTH_YELLOW;
    pinGreen  = PIN_NORTH_GREEN;
    targetState = &stateNorth;
  } else if (laneName.equalsIgnoreCase("South")) {
    pinRed    = PIN_SOUTH_RED;
    pinYellow = PIN_SOUTH_YELLOW;
    pinGreen  = PIN_SOUTH_GREEN;
    targetState = &stateSouth;
  } else if (laneName.equalsIgnoreCase("East")) {
    pinRed    = PIN_EAST_RED;
    pinYellow = PIN_EAST_YELLOW;
    pinGreen  = PIN_EAST_GREEN;
    targetState = &stateEast;
  } else if (laneName.equalsIgnoreCase("West")) {
    pinRed    = PIN_WEST_RED;
    pinYellow = PIN_WEST_YELLOW;
    pinGreen  = PIN_WEST_GREEN;
    targetState = &stateWest;
  } else {
    Serial.printf("[ESP32] Unknown lane specified: %s\n", laneName.c_str());
    return;
  }

  // 1. Safe state transition: turn off all 3 LEDs for this lane first
  digitalWrite(pinRed, LOW);
  digitalWrite(pinYellow, LOW);
  digitalWrite(pinGreen, LOW);

  // 2. Light only the commanded LED
  if (signal.equalsIgnoreCase("GREEN")) {
    digitalWrite(pinGreen, HIGH);
    *targetState = "GREEN";
  } else if (signal.equalsIgnoreCase("YELLOW")) {
    digitalWrite(pinYellow, HIGH);
    *targetState = "YELLOW";
  } else if (signal.equalsIgnoreCase("RED")) {
    digitalWrite(pinRed, HIGH);
    *targetState = "RED";
  } else if (signal.equalsIgnoreCase("OFF")) {
    *targetState = "OFF";
  } else {
    // Default safe fallback is RED
    digitalWrite(pinRed, HIGH);
    *targetState = "RED";
  }

  Serial.printf("[ESP32] Lane %s set to %s\n", laneName.c_str(), targetState->c_str());
}

void setSafeStateAllRed() {
  applyLaneSignal("North", "RED");
  applyLaneSignal("South", "RED");
  applyLaneSignal("East",  "RED");
  applyLaneSignal("West",  "RED");
  Serial.println("[ESP32] All lanes transitioned to safe state (ALL RED)");
}

void setAllOff() {
  applyLaneSignal("North", "OFF");
  applyLaneSignal("South", "OFF");
  applyLaneSignal("East",  "OFF");
  applyLaneSignal("West",  "OFF");
  Serial.println("[ESP32] All 12 LEDs turned OFF");
}

void sendCORSHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "*");
}

// ============================================================================
// HTTP ROUTE HANDLERS
// ============================================================================

void handleRoot() {
  sendCORSHeaders();
  String html = "<!DOCTYPE html><html><head><title>ESP32 Traffic Controller</title>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>body{font-family:sans-serif;background:#0a0f1e;color:#e0f0ff;padding:24px;text-align:center}";
  html += ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px;max-width:600px;margin:24px auto}";
  html += ".card{background:#131c2e;padding:16px;border-radius:12px;border:1px solid #1e2d4a}";
  html += ".status{font-weight:bold;font-size:18px;margin-top:8px}";
  html += ".btn{display:inline-block;padding:10px 20px;background:#00ff87;color:#0a0f1e;border-radius:8px;text-decoration:none;font-weight:bold;margin:6px}";
  html += "</style></head><body>";
  html += "<h2>🚦 ESP32 Traffic Signal Controller Online</h2>";
  html += "<p style='color:#7090b0'>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<div class='grid'>";
  html += "<div class='card'>North<div class='status' style='color:" + String(stateNorth == "GREEN" ? "#00ff87" : (stateNorth == "YELLOW" ? "#ffd32a" : "#ff4757")) + "'>" + stateNorth + "</div></div>";
  html += "<div class='card'>South<div class='status' style='color:" + String(stateSouth == "GREEN" ? "#00ff87" : (stateSouth == "YELLOW" ? "#ffd32a" : "#ff4757")) + "'>" + stateSouth + "</div></div>";
  html += "<div class='card'>East<div class='status' style='color:" + String(stateEast == "GREEN" ? "#00ff87" : (stateEast == "YELLOW" ? "#ffd32a" : "#ff4757")) + "'>" + stateEast + "</div></div>";
  html += "<div class='card'>West<div class='status' style='color:" + String(stateWest == "GREEN" ? "#00ff87" : (stateWest == "YELLOW" ? "#ffd32a" : "#ff4757")) + "'>" + stateWest + "</div></div>";
  html += "</div>";
  html += "<div><a class='btn' href='/reset'>Set Safe State (ALL RED)</a></div>";
  html += "<p style='font-size:12px;color:#4a7090;margin-top:20px'>ESP32 Traffic Signal Controller Online</p>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void handleStatusJson() {
  sendCORSHeaders();
  String json = "{";
  json += "\"status\":\"online\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"signals\":{";
  json += "\"North\":\"" + stateNorth + "\",";
  json += "\"South\":\"" + stateSouth + "\",";
  json += "\"East\":\""  + stateEast  + "\",";
  json += "\"West\":\""  + stateWest  + "\"";
  json += "},";
  json += "\"gpio\":{";
  json += "\"North\":{\"red\":" + String(PIN_NORTH_RED) + ",\"yellow\":" + String(PIN_NORTH_YELLOW) + ",\"green\":" + String(PIN_NORTH_GREEN) + "},";
  json += "\"South\":{\"red\":" + String(PIN_SOUTH_RED) + ",\"yellow\":" + String(PIN_SOUTH_YELLOW) + ",\"green\":" + String(PIN_SOUTH_GREEN) + "},";
  json += "\"East\":{\"red\":"  + String(PIN_EAST_RED)  + ",\"yellow\":" + String(PIN_EAST_YELLOW)  + ",\"green\":" + String(PIN_EAST_GREEN)  + "},";
  json += "\"West\":{\"red\":"  + String(PIN_WEST_RED)  + ",\"yellow\":" + String(PIN_WEST_YELLOW)  + ",\"green\":" + String(PIN_WEST_GREEN)  + "}";
  json += "}";
  json += "}";
  server.send(200, "application/json", json);
}

// Single lane control: /signal?lane=North&signal=GREEN
void handleSingleSignal() {
  sendCORSHeaders();
  if (!server.hasArg("lane") || !server.hasArg("signal")) {
    server.send(400, "application/json", "{\"error\":\"Missing required query params 'lane' and 'signal'\"}");
    return;
  }

  String lane = server.arg("lane");
  String signal = server.arg("signal");

  applyLaneSignal(lane, signal);

  String resp = "{\"success\":true,\"lane\":\"" + lane + "\",\"signal\":\"" + signal + "\"}";
  server.send(200, "application/json", resp);
}

// Atomic multi-lane control: /traffic?north=RED&south=GREEN&east=RED&west=RED
void handleTrafficUpdate() {
  sendCORSHeaders();

  if (server.hasArg("north")) applyLaneSignal("North", server.arg("north"));
  if (server.hasArg("south")) applyLaneSignal("South", server.arg("south"));
  if (server.hasArg("east"))  applyLaneSignal("East",  server.arg("east"));
  if (server.hasArg("west"))  applyLaneSignal("West",  server.arg("west"));

  String json = "{";
  json += "\"success\":true,";
  json += "\"signals\":{";
  json += "\"North\":\"" + stateNorth + "\",";
  json += "\"South\":\"" + stateSouth + "\",";
  json += "\"East\":\""  + stateEast  + "\",";
  json += "\"West\":\""  + stateWest  + "\"";
  json += "}";
  json += "}";
  server.send(200, "application/json", json);
}

// Safe state reset: /reset
void handleReset() {
  sendCORSHeaders();
  setSafeStateAllRed();
  server.send(200, "application/json", "{\"success\":true,\"state\":\"ALL_RED\",\"message\":\"Safe state activated\"}");
}

// All LEDs off: /all_off
void handleAllOff() {
  sendCORSHeaders();
  setAllOff();
  server.send(200, "application/json", "{\"success\":true,\"state\":\"ALL_OFF\"}");
}

void handleNotFound() {
  sendCORSHeaders();
  server.send(404, "application/json", "{\"error\":\"Endpoint not found\"}");
}

// ============================================================================
// SETUP & MAIN LOOP
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("==================================================");
  Serial.println("🚦 ESP32 DOIT DEVKIT V1 Traffic Signal Controller");
  Serial.println("==================================================");

  // Initialize all 12 GPIO pins as outputs
  pinMode(PIN_NORTH_RED, OUTPUT);
  pinMode(PIN_NORTH_YELLOW, OUTPUT);
  pinMode(PIN_NORTH_GREEN, OUTPUT);

  pinMode(PIN_SOUTH_RED, OUTPUT);
  pinMode(PIN_SOUTH_YELLOW, OUTPUT);
  pinMode(PIN_SOUTH_GREEN, OUTPUT);

  pinMode(PIN_EAST_RED, OUTPUT);
  pinMode(PIN_EAST_YELLOW, OUTPUT);
  pinMode(PIN_EAST_GREEN, OUTPUT);

  pinMode(PIN_WEST_RED, OUTPUT);
  pinMode(PIN_WEST_YELLOW, OUTPUT);
  pinMode(PIN_WEST_GREEN, OUTPUT);

  // Initial boot state: ALL RED (Safe)
  setSafeStateAllRed();

  // Connect to Wi-Fi
  Serial.printf("Connecting to Wi-Fi SSID: %s ", ssid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println("==================================================");
  } else {
    Serial.println("⚠️ Wi-Fi connection timed out. Check SSID/Password.");
    Serial.println("ESP32 will continue in standalone safe mode.");
    Serial.println("==================================================");
  }

  // Register Web Server Routes
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatusJson);
  server.on("/signal", HTTP_GET, handleSingleSignal);
  server.on("/traffic", HTTP_GET, handleTrafficUpdate);
  server.on("/reset", HTTP_GET, handleReset);
  server.on("/all_off", HTTP_GET, handleAllOff);
  server.onNotFound(handleNotFound);

  // Start HTTP Server
  server.begin();
  Serial.println("HTTP server started on port 80");
}

void loop() {
  server.handleClient();
}
