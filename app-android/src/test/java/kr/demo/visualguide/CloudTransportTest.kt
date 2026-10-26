package kr.demo.visualguide

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.net.URL
import java.security.cert.Certificate
import javax.net.ssl.HttpsURLConnection

class CloudTransportTest {
    private class Response(url: URL, private val code: Int) : HttpsURLConnection(url) {
        var disconnected = false
        override fun getResponseCode() = code
        override fun getOutputStream() = ByteArrayOutputStream()
        override fun connect() = Unit
        override fun disconnect() { disconnected = true }
        override fun usingProxy() = false
        override fun getCipherSuite() = "test-only"
        override fun getLocalCertificates(): Array<Certificate>? = null
        override fun getServerCertificates(): Array<Certificate> = emptyArray()
    }

    @Test fun authenticatedRedirectIsAnErrorAndNeverFollowed() {
        val connection = Response(URL("https://example.org/v1/catalog"), 302)
        val api = CloudApiClient(ApiEndpoint.parse("https://example.org"), "opaque-device-token-123") { connection }
        val failure = assertThrows(CloudApiException::class.java) { runBlocking { api.catalog() } }
        assertTrue(failure.message!!.contains("302"))
        assertFalse(connection.instanceFollowRedirects)
        assertEquals("Bearer opaque-device-token-123", connection.getRequestProperty("Authorization"))
        assertTrue(connection.disconnected)
    }

    @Test fun unavailableCloudIsNotADemoCatalog() {
        val connection = Response(URL("https://example.org/v1/catalog"), 503)
        val api = CloudApiClient(ApiEndpoint.parse("https://example.org"), "opaque-device-token-123") { connection }
        assertThrows(CloudApiException::class.java) { runBlocking { api.catalog() } }
        assertTrue(connection.disconnected)
    }

    @Test fun tokenHeaderInjectionIsRejectedBeforeConnecting() {
        assertThrows(IllegalArgumentException::class.java) {
            CloudApiClient(ApiEndpoint.parse("https://example.org"), "opaque-token\r\nInjected: yes")
        }
    }

    @Test fun pairingRejectsCodesOutsideServerLimitsBeforeConnecting() {
        var connections = 0
        val api = CloudApiClient(ApiEndpoint.parse("https://example.org")) { url ->
            connections++
            Response(url, 503)
        }
        listOf(7, 257).forEach { length ->
            assertThrows(IllegalArgumentException::class.java) {
                runBlocking { api.pair("x".repeat(length)) }
            }
        }
        assertEquals(0, connections)
    }

    @Test fun pairingAcceptsBothServerBoundaryLengths() {
        var connections = 0
        val api = CloudApiClient(ApiEndpoint.parse("https://example.org")) { url ->
            connections++
            Response(url, 503)
        }
        listOf(8, 256).forEach { length ->
            assertThrows(CloudApiException::class.java) {
                runBlocking { api.pair("x".repeat(length)) }
            }
        }
        assertEquals(2, connections)
    }
}
