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
            ],
          ),
        ),
      ),
    );
  }
}
