package za.co.louw.nutribalance.louw_forum

import android.app.Activity
import android.content.Intent
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.android.FlutterActivity
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channelName = "louw_forum/files"
    private val pickerRequest = 4107
    private var pendingPicker: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName).setMethodCallHandler { call, result ->
            if (call.method != "chooseImages") {
                result.notImplemented()
            } else if (pendingPicker != null) {
                result.error("picker_busy", "Finish choosing the current photos first.", null)
            } else {
                pendingPicker = result
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "image/*"
                    putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/jpeg", "image/png", "image/webp"))
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, call.argument<Boolean>("multiple") == true)
                }
                try {
                    startActivityForResult(intent, pickerRequest)
                } catch (error: Exception) {
                    pendingPicker = null
                    result.error("picker_unavailable", "The Android photo picker is unavailable.", null)
                }
            }
        }
    }

    @Deprecated("Android activity result callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != pickerRequest) return
        val images = mutableListOf<String>()
        if (resultCode == Activity.RESULT_OK) {
            data?.clipData?.let { clips ->
                for (index in 0 until clips.itemCount) images.add(clips.getItemAt(index).uri.toString())
            }
            if (images.isEmpty()) data?.data?.let { images.add(it.toString()) }
        }
        pendingPicker?.success(images)
        pendingPicker = null
    }
}
