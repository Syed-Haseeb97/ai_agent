# Ruby-side tool definitions for the local Amazon connector.
# The Python service must be running on 127.0.0.1:8765.
require "json"
require "net/http"
require "uri"

module AmazonTools
  BASE_URL = "http://127.0.0.1:8765"

  def self.get(path)
    uri = URI("#{BASE_URL}#{path}")
    response = Net::HTTP.get_response(uri)
    JSON.parse(response.body)
  end

  def self.post(path, payload)
    uri = URI("#{BASE_URL}#{path}")
    http = Net::HTTP.new(uri.host, uri.port)
    request = Net::HTTP::Post.new(uri.request_uri)
    request["Content-Type"] = "application/json"
    request.body = JSON.generate(payload)
    response = http.request(request)
    JSON.parse(response.body)
  end

  def self.amazon_status
    get("/amazon/status")
  end

  def self.amazon_list_orders
    get("/amazon/orders")
  end

  def self.amazon_find_order(query)
    post("/amazon/find-order", { query: query })
  end

  def self.amazon_track_order(order_id)
    post("/amazon/track", { order_id: order_id })
  end

  def self.amazon_cancel_order(order_id, confirmed: false)
    post("/amazon/cancel", { order_id: order_id, confirmed: confirmed })
  end
end

# Gemini-compatible function declarations. Keep cancellation explicitly
# confirmation-gated so the model cannot silently perform a destructive action.
AMAZON_TOOLS = [
  {
    name: "amazon_list_orders",
    description: "Retrieve recent Amazon.in orders. Read-only.",
    parameters: { type: "object", properties: {}, required: [] }
  },
  {
    name: "amazon_find_order",
    description: "Find a user's Amazon.in order by item name, order ID, or descriptive query. Read-only.",
    parameters: {
      type: "object",
      properties: { query: { type: "string" } },
      required: ["query"]
    }
  },
  {
    name: "amazon_track_order",
    description: "Retrieve the current status/details of a specific Amazon.in order. Read-only.",
    parameters: {
      type: "object",
      properties: { order_id: { type: "string" } },
      required: ["order_id"]
    }
  },
  {
    name: "amazon_cancel_order",
    description: "Cancel a specific Amazon.in order. Destructive: only call after explicit user confirmation in the current conversation, and pass confirmed=true.",
    parameters: {
      type: "object",
      properties: {
        order_id: { type: "string" },
        confirmed: { type: "boolean" }
      },
      required: ["order_id", "confirmed"]
    }
  }
]
