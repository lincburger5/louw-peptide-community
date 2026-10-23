import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

const defaultServer = 'http://127.0.0.1:5000/';
const forest = Color(0xFF123B2A);
const gold = Color(0xFF8A5A12);

bool isAllowedServerAddress(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !uri.hasAuthority ||
      (uri.scheme != 'http' && uri.scheme != 'https')) {
    return false;
  }
  if (uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      uri.path != '/' && uri.path.isNotEmpty) {
    return false;
  }
  if (uri.scheme == 'https') return true;
  final host = uri.host.toLowerCase();
  if (host == 'localhost' || host == '127.0.0.1') return true;
  final parts = host.split('.').map(int.tryParse).toList();
  if (parts.length != 4 ||
      parts.any((part) => part == null || part < 0 || part > 255)) {
    return false;
  }
  return parts[0] == 10 ||
      (parts[0] == 192 && parts[1] == 168) ||
      (parts[0] == 172 && parts[1]! >= 16 && parts[1]! <= 31);
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: forest,
      statusBarIconBrightness: Brightness.light,
    ),
  );
  runApp(const ForumApp());
}

class ForumApp extends StatelessWidget {
  const ForumApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Louw Forum (Local)',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: forest),
      appBarTheme: const AppBarTheme(
        backgroundColor: forest,
        foregroundColor: Colors.white,
        centerTitle: false,
      ),
    ),
    home: const ForumScreen(),
  );
}

class ForumScreen extends StatefulWidget {
  const ForumScreen({super.key});

  @override
  State<ForumScreen> createState() => _ForumScreenState();
}

class _ForumScreenState extends State<ForumScreen> {
  static const files = MethodChannel('louw_forum/files');
  WebViewController? controller;
  String server = defaultServer;
  String? error;
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _loadSavedServer();
  }

  Future<void> _loadSavedServer() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('server') ?? defaultServer;
    if (!mounted) return;
    setState(() => server = saved);
    _openServer(saved);
  }

  Future<void> _openServer(String address) async {
    setState(() {
      loading = true;
      error = null;
    });
    final origin = Uri.parse(address).origin;
    final web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.white)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) {
            if (mounted) {
              setState(() {
                loading = true;
                error = null;
              });
            }
          },
          onPageFinished: (_) {
            if (mounted) setState(() => loading = false);
          },
          onWebResourceError: (problem) {
            if (problem.isForMainFrame == true && mounted) {
              setState(() {
                loading = false;
                error = 'Could not reach the forum on this laptop.';
              });
            }
          },
          onNavigationRequest: (request) {
            if (Uri.tryParse(request.url)?.origin == origin) {
              return NavigationDecision.navigate;
            }
            return NavigationDecision.prevent;
          },
        ),
      );
    if (web.platform is AndroidWebViewController) {
      await (web.platform as AndroidWebViewController).setOnShowFileSelector((
        params,
      ) async {
        try {
          return await files.invokeListMethod<String>('chooseImages', {
                'multiple': params.mode == FileSelectorMode.openMultiple,
              }) ??
              <String>[];
        } on PlatformException {
          return <String>[];
        }
      });
    }
    if (!mounted) return;
    setState(() => controller = web);
    await web.loadRequest(Uri.parse(address));
  }

  Future<void> _settings() async {
    final input = TextEditingController(text: server);
    String? validation;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, update) => Padding(
          padding: EdgeInsets.fromLTRB(
            22,
            8,
            22,
            MediaQuery.viewInsetsOf(sheetContext).bottom + 30,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Laptop connection',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 6),
              const Text(
                'The forum and its data stay on your laptop. Keep the server running. USB testing uses the default address; Wi-Fi needs your laptop’s local address.',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: input,
                keyboardType: TextInputType.url,
                autocorrect: false,
                decoration: InputDecoration(
                  labelText: 'Forum address',
                  hintText: defaultServer,
                  errorText: validation,
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () async {
                    var value = input.text.trim();
                    if (!value.endsWith('/')) value += '/';
                    if (!isAllowedServerAddress(value)) {
                      update(
                        () => validation =
                            'Use localhost, a private Wi-Fi address, or HTTPS.',
                      );
                      return;
                    }
                    final prefs = await SharedPreferences.getInstance();
                    await prefs.setString('server', value);
                    if (!mounted || !sheetContext.mounted) return;
                    setState(() => server = value);
                    Navigator.pop(sheetContext);
                    await _openServer(value);
                  },
                  child: const Text('Connect'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    input.dispose();
  }

  Future<void> _back() async {
    if (await controller?.canGoBack() == true) {
      await controller?.goBack();
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    onPopInvokedWithResult: (didPop, result) {
      if (!didPop) _back();
    },
    child: Scaffold(
      appBar: AppBar(
        title: const Text(
          'LOUW  ·  Forum',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
            letterSpacing: 1,
          ),
        ),
        actions: [
          IconButton(
            tooltip: 'Refresh forum',
            icon: const Icon(Icons.refresh),
            onPressed: () => controller?.reload(),
          ),
          IconButton(
            tooltip: 'Laptop connection',
            icon: const Icon(Icons.settings_outlined),
            onPressed: _settings,
          ),
        ],
      ),
      body: Stack(
        children: [
          if (controller != null) WebViewWidget(controller: controller!),
          if (loading)
            const Align(
              alignment: Alignment.topCenter,
              child: LinearProgressIndicator(color: gold, minHeight: 3),
            ),
          if (error != null)
            Positioned.fill(
              child: ColoredBox(
                color: Colors.white,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.wifi_off_rounded,
                          color: forest,
                          size: 46,
                        ),
                        const SizedBox(height: 14),
                        Text(
                          error!,
                          style: Theme.of(context).textTheme.titleMedium,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text('Server: $server', textAlign: TextAlign.center),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: () => _openServer(server),
                          icon: const Icon(Icons.refresh),
                          label: const Text('Try again'),
                        ),
                        TextButton(
                          onPressed: _settings,
                          child: const Text('Change address'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}
