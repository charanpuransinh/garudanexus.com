import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

// HTTPS on purpose (not the plain-HTTP IP address) — this domain sits
// behind a site-wide PIN gate (nginx redirects to pin.html if the
// trishul_pin cookie isn't set yet). A WebView handles that redirect and
// the PIN form the same as any browser would: it shows pin.html first,
// the user types the PIN once, and the cookie takes them to the dashboard
// from then on. That's simpler and more robust than switching to the raw
// HTTP IP, which would need extra Android manifest changes to allow
// cleartext traffic.
const String dashboardUrl = 'https://garudanexus.com/trading-bot/dashboard.html';

void main() {
  runApp(const TradingBotApp());
}

class TradingBotApp extends StatelessWidget {
  const TradingBotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Trading Bot',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        primaryColor: const Color(0xFFF5C518),
        scaffoldBackgroundColor: Colors.black,
      ),
      home: const DashboardScreen(),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late final WebViewController _controller;
  bool _loading = true;
  String? _errorMessage;

  void _load() {
    setState(() => _errorMessage = null);
    _controller.loadRequest(Uri.parse(dashboardUrl));
  }

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) => setState(() => _loading = true),
          onPageFinished: (_) => setState(() => _loading = false),
          // BUG FIX (2026-07-25): previously any load failure (missing
          // INTERNET permission, no signal, DNS/SSL failure) just left the
          // screen on its plain black background forever with zero
          // indication of what went wrong. Now the actual error is shown,
          // with a retry button.
          onWebResourceError: (error) {
            if (error.isForMainFrame ?? true) {
              setState(() {
                _loading = false;
                _errorMessage = '${error.errorCode}: ${error.description}';
              });
            }
          },
        ),
      )
      ..loadRequest(Uri.parse(dashboardUrl));
  }

  Future<bool> _onWillPop() async {
    if (await _controller.canGoBack()) {
      _controller.goBack();
      return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: _onWillPop,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_loading)
                const Center(
                  child: CircularProgressIndicator(color: Color(0xFFF5C518)),
                ),
              if (_errorMessage != null)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off, color: Colors.white54, size: 40),
                        const SizedBox(height: 12),
                        Text(
                          'Dashboard load नहीं हो पाया:\n$_errorMessage',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white70),
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: _load,
                          child: const Text('फिर कोशिश करो'),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
