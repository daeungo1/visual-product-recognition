package kr.demo.visualguide

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kr.demo.guide.OcrEvidence
import java.util.concurrent.atomic.AtomicReference

@Composable
internal fun CameraPermissionHost(
    activity: ComponentActivity,
    assets: DemoAssets?,
    capture: AtomicReference<CaptureRequest?>,
    generation: Int,
    onFrame: (OverlayFrame) -> Unit,
    onOcr: (OcrEvidence) -> Unit,
    onStatus: (String) -> Unit,
    onOcrStatus: (String) -> Unit,
    snapshots: CameraSnapshotChannel? = null,
    discoveryTargets: List<DemoAssets> = emptyList(),
) {
    fun permissionGranted() = activity.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    var granted by remember { mutableStateOf(permissionGranted()) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        granted = it
        if (!it) onStatus("카메라 권한 거부됨. 수동 안내는 가능합니다.")
    }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) granted = permissionGranted()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    if (!granted) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("AR 미리보기에는 카메라 권한이 필요합니다.", color = Color.White)
            Button(onClick = { launcher.launch(Manifest.permission.CAMERA) }) { Text("카메라 권한 요청") }
            OutlinedButton(onClick = {
                activity.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${activity.packageName}")))
            }) { Text("앱 권한 설정 열기") }
        }
    } else {
        val controller = remember(assets, generation, discoveryTargets) {
            ArCameraController(activity, assets, capture, onFrame, onOcr, onOcrStatus, onStatus, snapshots, discoveryTargets)
        }
        key(controller) {
            AndroidView(factory = { controller.surface }, modifier = Modifier.fillMaxSize())
        }
        DisposableEffect(controller, owner) {
            val observer = LifecycleEventObserver { _, event ->
                when (event) {
                    Lifecycle.Event.ON_RESUME -> controller.resume()
                    Lifecycle.Event.ON_PAUSE -> controller.pause()
                    else -> Unit
                }
            }
            owner.lifecycle.addObserver(observer)
            onDispose {
                owner.lifecycle.removeObserver(observer)
                controller.close()
            }
        }
    }
}
