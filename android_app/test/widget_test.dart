import 'package:flutter_test/flutter_test.dart';
import 'package:louw_forum/main.dart';

void main() {
  test('accepts USB loopback and private Wi-Fi forum addresses', () {
    expect(isAllowedServerAddress('http://127.0.0.1:5000/'), isTrue);
    expect(isAllowedServerAddress('http://192.168.1.10:5000/'), isTrue);
    expect(isAllowedServerAddress('http://10.0.0.2:5000/'), isTrue);
    expect(isAllowedServerAddress('http://172.16.2.4:5000/'), isTrue);
  });

  test('rejects arbitrary cleartext hosts and embedded credentials', () {
    expect(isAllowedServerAddress('http://example.com/'), isFalse);
    expect(isAllowedServerAddress('http://user:pass@127.0.0.1:5000/'), isFalse);
    expect(isAllowedServerAddress('http://192.168.1.10:5000/other'), isFalse);
    expect(isAllowedServerAddress('javascript:alert(1)'), isFalse);
  });
}
