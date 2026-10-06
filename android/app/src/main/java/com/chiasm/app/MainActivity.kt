package com.chiasm.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder


data class Track(
    val providerId: String,
    val trackId: String,
    val title: String,
    val artist: String,
    val album: String = "",
    val streamUrl: String = ""
)

class BridgeClient(var baseUrl: String, var token: String) {
    private fun get(path: String): JSONObject {
        val conn = URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 8000
        conn.readTimeout = 15000
        if (token.isNotBlank()) conn.setRequestProperty("Authorization", "Bearer $token")
        conn.setRequestProperty("Accept", "application/json")
        val code = conn.responseCode
        val body = (if (code in 200..299) conn.inputStream else conn.errorStream).bufferedReader().use { it.readText() }
        if (code !in 200..299) throw IllegalStateException("Bridge error $code: $body")
        return JSONObject(body)
    }

    fun health(): Boolean = get("/health").optBoolean("ok", false)

    fun search(query: String): List<Track> {
        val q = URLEncoder.encode(query, "UTF-8")
        val json = get("/v1/search?q=$q&provider=all")
        val arr = json.optJSONArray("items") ?: return emptyList()
        return buildList {
            for (i in 0 until arr.length()) {
                val x = arr.getJSONObject(i)
                add(Track(
                    providerId = x.optString("provider_id"),
                    trackId = x.optString("track_id"),
                    title = x.optString("title", "Unknown track"),
                    artist = x.optString("artist", "Unknown artist"),
                    album = x.optString("album"),
                    streamUrl = x.optString("stream_url")
                ))
            }
        }
    }

    fun resolve(track: Track): Track {
        val p = URLEncoder.encode(track.providerId, "UTF-8")
        val id = URLEncoder.encode(track.trackId, "UTF-8")
        val x = get("/v1/resolve?provider=$p&id=$id")
        return track.copy(
            title = x.optString("title", track.title),
            artist = x.optString("artist", track.artist),
            album = x.optString("album", track.album),
            streamUrl = x.optString("stream_url", track.streamUrl)
        )
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val player = ExoPlayer.Builder(this).build()
        setContent { ChiasmApp(player) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChiasmApp(player: ExoPlayer) {
    var bridgeUrl by remember { mutableStateOf("http://192.168.1.2:8766") }
    var token by remember { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("Connect to Chiasm on your computer or NAS.") }
    var results by remember { mutableStateOf<List<Track>>(emptyList()) }
    var nowPlaying by remember { mutableStateOf<Track?>(null) }
    val scope = rememberCoroutineScope()

    MaterialTheme(colorScheme = darkColorScheme()) {
        Scaffold(topBar = { TopAppBar(title = { Text("Chiasm") }) }) { pad ->
            Column(Modifier.padding(pad).padding(16.dp).fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Explore your music.", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(bridgeUrl, { bridgeUrl = it }, label = { Text("Bridge URL") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(token, { token = it }, label = { Text("Bridge token") }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        scope.launch {
                            status = "Connecting…"
                            status = try {
                                val ok = withContext(Dispatchers.IO) { BridgeClient(bridgeUrl, token).health() }
                                if (ok) "Connected." else "Bridge did not report healthy."
                            } catch (e: Exception) { e.message ?: "Connection failed" }
                        }
                    }) { Text("Connect") }
                    Text(status, modifier = Modifier.align(Alignment.CenterVertically))
                }
                Divider()
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(query, { query = it }, label = { Text("Search your connected music") }, modifier = Modifier.weight(1f))
                    Button(onClick = {
                        scope.launch {
                            status = "Searching…"
                            try {
                                results = withContext(Dispatchers.IO) { BridgeClient(bridgeUrl, token).search(query) }
                                status = "${results.size} results"
                            } catch (e: Exception) { status = e.message ?: "Search failed" }
                        }
                    }) { Text("Search") }
                }
                nowPlaying?.let { Text("Now playing: ${it.artist} — ${it.title}", style = MaterialTheme.typography.titleSmall) }
                LazyColumn(Modifier.weight(1f)) {
                    items(results) { track ->
                        ListItem(
                            headlineContent = { Text(track.title) },
                            supportingContent = { Text("${track.artist}${if (track.album.isNotBlank()) " · ${track.album}" else ""}") },
                            modifier = Modifier.clickable {
                                scope.launch {
                                    status = "Resolving…"
                                    try {
                                        val resolved = withContext(Dispatchers.IO) { BridgeClient(bridgeUrl, token).resolve(track) }
                                        if (resolved.streamUrl.isBlank()) throw IllegalStateException("Source did not return a stream URL")
                                        player.setMediaItem(MediaItem.fromUri(resolved.streamUrl))
                                        player.prepare(); player.play()
                                        nowPlaying = resolved; status = "Playing"
                                    } catch (e: Exception) { status = e.message ?: "Playback failed" }
                                }
                            }
                        )
                        Divider()
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { if (player.isPlaying) player.pause() else player.play() }) { Text("Play / Pause") }
                    Button(onClick = { player.seekTo(0) }) { Text("Restart") }
                }
            }
        }
    }
}
