package handlers

import (
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
)

func RegisterHealth(router *gin.Engine) {
	router.GET("/", rootHandler)
	router.GET("/health", healthHandler)
}

func rootHandler(c *gin.Context) {
	templatePath := filepath.Join("src", "superbox", "server", "templates", "index.html")
	content, err := os.ReadFile(templatePath)
	if err != nil {
		c.HTML(http.StatusOK, "index.html", gin.H{
			"title": "SuperBox API Server",
		})
		return
	}
	c.Data(http.StatusOK, "text/html; charset=utf-8", content)
}

func healthHandler(c *gin.Context) {
	cfgOk := true
	s3Ok := false
	registryOk := false

	requiredVars := []string{
		"SUPERBOX_API_URL",
		"AWS_REGION",
		"AWS_ACCESS_KEY_ID",
		"AWS_SECRET_ACCESS_KEY",
		"S3_BUCKET_NAME",
		"FIREBASE_API_KEY",
		"FIREBASE_PROJECT_ID",
		"RAZORPAY_KEY_ID",
		"RAZORPAY_KEY_SECRET",
	}

	for _, v := range requiredVars {
		if os.Getenv(v) == "" {
			cfgOk = false
			break
		}
	}

	if cfgOk {
		s3Ok = true
		registryOk = true
	}

	status := "healthy"
	if !cfgOk || !s3Ok {
		status = "degraded"
	}

	c.JSON(http.StatusOK, gin.H{
		"status":       status,
		"version":      "1.0.0",
		"config_ok":    cfgOk,
		"s3_client_ok": s3Ok,
		"registry_ok":  registryOk,
	})
}
