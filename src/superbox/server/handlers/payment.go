package handlers

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"

	"superbox/server/models"

	"github.com/gin-gonic/gin"
)

var razorpayKeyID string
var razorpayKeySecret string

func init() {
	razorpayKeyID = os.Getenv("RAZORPAY_KEY_ID")
	razorpayKeySecret = os.Getenv("RAZORPAY_KEY_SECRET")
}

func RegisterPayment(api *gin.RouterGroup) {
	payment := api.Group("/payment")
	{
		payment.POST("/create-order", createOrder)
		payment.POST("/verify-payment", verifyPayment)
		payment.GET("/payment-status/:payment_id", getPaymentStatus)
	}
}

func createOrder(c *gin.Context) {
	var req models.CreateOrderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.OrderResponse{
			Status: "error",
			Detail: "Invalid request: " + err.Error(),
		})
		return
	}

	amountInSubunits := int(req.Amount * 100)
	currencyUpper := strings.ToUpper(req.Currency)

	orderData := map[string]interface{}{
		"amount":   amountInSubunits,
		"currency": currencyUpper,
		"receipt":  fmt.Sprintf("order_%s_%d", req.ServerName, amountInSubunits),
		"notes": map[string]interface{}{
			"server_name": req.ServerName,
		},
	}

	order, err := razorpayCreateOrder(orderData)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.OrderResponse{
			Status: "error",
			Detail: "Error creating order: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.OrderResponse{
		Status: "success",
		Order: map[string]interface{}{
			"id":       order["id"],
			"amount":   order["amount"],
			"currency": order["currency"],
		},
		KeyID: razorpayKeyID,
	})
}

func verifyPayment(c *gin.Context) {
	var req models.VerifyPaymentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.PaymentResponse{
			Status: "error",
			Detail: "Invalid request: " + err.Error(),
		})
		return
	}

	message := fmt.Sprintf("%s|%s", req.RazorpayOrderID, req.RazorpayPaymentID)
	mac := hmac.New(sha256.New, []byte(razorpayKeySecret))
	mac.Write([]byte(message))
	generatedSignature := hex.EncodeToString(mac.Sum(nil))

	if generatedSignature == req.RazorpaySignature {
		c.JSON(http.StatusOK, models.PaymentResponse{
			Status:  "success",
			Message: "Payment verified",
			Payment: map[string]interface{}{
				"id":          req.RazorpayPaymentID,
				"server_name": req.ServerName,
			},
		})
		return
	}

	c.JSON(http.StatusBadRequest, models.PaymentResponse{
		Status: "error",
		Detail: "Invalid payment signature",
	})
}

func getPaymentStatus(c *gin.Context) {
	paymentID := c.Param("payment_id")

	payment, err := razorpayGetPayment(paymentID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.PaymentResponse{
			Status: "error",
			Detail: "Error fetching payment status: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.PaymentResponse{
		Status: "success",
		Payment: map[string]interface{}{
			"id":       payment["id"],
			"state":    payment["status"],
			"amount":   payment["amount"],
			"currency": payment["currency"],
			"method":   payment["method"],
			"email":    payment["email"],
			"contact":  payment["contact"],
		},
	})
}

func razorpayCreateOrder(orderData map[string]interface{}) (map[string]interface{}, error) {
	url := "https://api.razorpay.com/v1/orders"

	jsonData, err := json.Marshal(orderData)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, strings.NewReader(string(jsonData)))
	if err != nil {
		return nil, err
	}

	req.SetBasicAuth(razorpayKeyID, razorpayKeySecret)
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&errorResp)
		return nil, fmt.Errorf("razorpay API error: %v", errorResp)
	}

	var order map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&order); err != nil {
		return nil, err
	}

	return order, nil
}

func razorpayGetPayment(paymentID string) (map[string]interface{}, error) {
	url := fmt.Sprintf("https://api.razorpay.com/v1/payments/%s", paymentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	req.SetBasicAuth(razorpayKeyID, razorpayKeySecret)

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&errorResp)
		return nil, fmt.Errorf("razorpay API error: %v", errorResp)
	}

	var payment map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&payment); err != nil {
		return nil, err
	}

	return payment, nil
}
