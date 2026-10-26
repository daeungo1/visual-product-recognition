package kr.demo.visualguide

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class CloudContractTest {
    @Test fun serverAcceptedGuideBoundariesRemainReadableOnAndroid() {
        val steps = JSONArray()
        repeat(128) { index ->
            steps.put(JSONObject("""{"id":"step-$index","button_id":"power","instruction":"전원","expected_display":"POWER ON"}"""))
        }
        val guide = CloudDtos.guide(JSONObject(GUIDE).put("title", "G".repeat(500)).put("steps", steps))
        assertEquals(500, guide.title.length)
        assertEquals(128, guide.steps.size)
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.guide(JSONObject(GUIDE).put("title", "G".repeat(501)))
        }
        steps.put(JSONObject("""{"id":"step-128","button_id":"power","instruction":"전원","expected_display":"POWER ON"}"""))
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.guide(JSONObject(GUIDE).put("steps", steps))
        }
    }

    @Test fun endpointRejectsInsecureAndAmbiguousOrigins() {
        listOf("http://example.org", "https://user:pass@example.org", "https://example.org/v1",
            "https://example.org?token=x", "https://example.org/#fragment", "//example.org").forEach {
            assertThrows(IllegalArgumentException::class.java) { ApiEndpoint.parse(it) }
        }
        assertEquals("https://example.org", ApiEndpoint.parse("https://EXAMPLE.org/").origin)
    }

    @Test fun referenceCannotExfiltrateBearerEvenWithSameHostTricks() {
        val endpoint = ApiEndpoint.parse("https://example.org")
        listOf("https://evil.org/v1/models/demo/reference", "//evil.org/x",
            "https://example.org/v1/models/demo/reference", "/v1/models/other/reference",
            "/v1/models/demo/reference?redirect=x", "/v1/models/demo/../other/reference").forEach {
            assertThrows(IllegalArgumentException::class.java) { endpoint.reference("demo", it) }
        }
        assertEquals("https://example.org/v1/models/demo/reference",
            endpoint.reference("demo", "/v1/models/demo/reference").toString())
    }

    @Test fun guideModelAndSessionMustAgree() {
        val guide = CloudDtos.guide(JSONObject(GUIDE))
        assertTrue(guide.demo)
        val model = CloudDtos.model(JSONObject(MODEL), ApiEndpoint.parse("https://example.org"))
        model.validate(guide)
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.model(JSONObject(MODEL).put("display",
                JSONObject("""{"left":0.9,"top":0.1,"right":0.2,"bottom":0.3}""")),
                ApiEndpoint.parse("https://example.org"))
        }
        val session = CloudDtos.session(JSONObject(
            """{"id":"session-1","guide_id":"demo-aircon","step_index":0,"current_step_id":"power","finished":false,"demo":true}"""
        ))
        session.validate(guide)
        assertThrows(IllegalArgumentException::class.java) {
            session.copy(currentStepId = "wrong").validate(guide)
        }
    }

    @Test fun unknownAndUnregisteredCandidatesNeverBecomeSuccess() {
        val catalog = listOf(CloudDtos.guide(JSONObject(GUIDE)))
        assertTrue(CloudDtos.identification(JSONObject(
            """{"status":"unknown","requires_confirmation":false,"candidates":[],"provider":"real"}"""
        ), catalog).candidates.isEmpty())
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.identification(JSONObject(
                """{"status":"candidates","requires_confirmation":true,"provider":"real","candidates":[{"product_id":"invented","model":"invented","target_id":"unknown","guide_ids":["unknown"],"search_score":1,"demo":false}]}"""
            ), catalog)
        }
    }

    @Test fun pendingEventRetainsExactUuidAndPayloadAcrossRetrySerialization() {
        val event = CloudEvent("6dc8b9ed-3562-4fee-bfb2-e03280f4aad1", "power", "ocr", "POWER ON", null)
        val restored = CloudDtos.event(JSONObject(event.json().toString()))
        assertEquals(event, restored)
        assertEquals(event.eventId, restored.eventId)
        assertEquals(event.json().toString(), restored.json().toString())
    }

    @Test fun failedOrWrongStepVerificationCannotSupplyAdvanceProof() {
        val unsure = JSONObject(
            """{"status":"unsure","step_id":"power","reason":"Glare","verification_id":null,"expires_in":0,"model_deployment":"actual-deployment"}"""
        )
        assertNull(CloudDtos.verification(unsure, "power").proof)
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.verification(unsure.put("verification_id", "unusable-proof"), "power")
        }
        assertThrows(IllegalArgumentException::class.java) {
            CloudDtos.verification(unsure.put("status", "pass").put("expires_in", 30), "mode")
        }
    }

    companion object {
        const val GUIDE = """{"id":"demo-aircon","target_id":"demo","title":"DEMO","demo":true,"steps":[{"id":"power","button_id":"power","instruction":"전원","expected_display":"POWER ON"}]}"""
        const val MODEL = """{"id":"demo","reference_width_m":0.16,"reference_image_url":"/v1/models/demo/reference","image_width":400,"image_height":640,"display":{"left":0.1,"top":0.1,"right":0.9,"bottom":0.3},"buttons":{"power":{"left":0.1,"top":0.4,"right":0.9,"bottom":0.5}}}"""
    }
}
