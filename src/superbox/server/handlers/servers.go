package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"superbox/server/models"

	"github.com/gin-gonic/gin"
)

func RegisterServers(api *gin.RouterGroup) {
	servers := api.Group("/servers")
	{
		servers.GET("", listServers)
		servers.GET("/:server_name", getServer)
		servers.POST("", createServer)
		servers.PUT("/:server_name", updateServer)
		servers.DELETE("/:server_name", deleteServer)
	}
}

func callPythonS3(function string, args map[string]interface{}) (map[string]interface{}, error) {
	scriptPath := filepath.Join("src", "superbox", "server", "helpers", "s3_helper.py")

	argsJSON, err := json.Marshal(map[string]interface{}{
		"function": function,
		"args":     args,
	})
	if err != nil {
		return nil, err
	}

	cmd := exec.Command("python", scriptPath, string(argsJSON))
	cmd.Env = os.Environ()
	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("python s3 call failed: %v", err)
	}

	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, fmt.Errorf("failed to parse python output: %v", err)
	}

	if errMsg, ok := result["error"].(string); ok {
		return nil, fmt.Errorf("%s", errMsg)
	}

	return result, nil
}

func getServer(c *gin.Context) {
	serverName := c.Param("server_name")
	bucketName := os.Getenv("S3_BUCKET_NAME")

	result, err := callPythonS3("get_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": serverName,
	})
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"status": "error",
			"detail": "Server '" + serverName + "' not found",
		})
		return
	}

	server, ok := result["data"].(map[string]interface{})
	if !ok || server == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"status": "error",
			"detail": "Server '" + serverName + "' not found",
		})
		return
	}

	c.JSON(http.StatusOK, models.ServerResponse{
		Status: "success",
		Server: server,
	})
}

func listServers(c *gin.Context) {
	bucketName := os.Getenv("S3_BUCKET_NAME")

	result, err := callPythonS3("list_servers", map[string]interface{}{
		"bucket_name": bucketName,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status": "error",
			"detail": "Error fetching servers: " + err.Error(),
		})
		return
	}

	serversMap, ok := result["data"].(map[string]interface{})
	if !ok {
		c.JSON(http.StatusOK, models.ServerResponse{
			Status:  "success",
			Total:   0,
			Servers: []interface{}{},
		})
		return
	}

	serverList := make([]interface{}, 0)
	for _, serverVal := range serversMap {
		server, ok := serverVal.(map[string]interface{})
		if !ok {
			continue
		}

		serverInfo := map[string]interface{}{
			"name":        server["name"],
			"version":     server["version"],
			"description": server["description"],
			"author":      server["author"],
			"lang":        server["lang"],
			"license":     server["license"],
			"entrypoint":  server["entrypoint"],
			"repository":  server["repository"],
		}

		if tools, ok := server["tools"].(map[string]interface{}); ok && tools != nil {
			serverInfo["tools"] = tools
		}

		if pricing, ok := server["pricing"].(map[string]interface{}); ok && pricing != nil {
			serverInfo["pricing"] = pricing
		} else {
			serverInfo["pricing"] = map[string]interface{}{
				"currency": "",
				"amount":   0,
			}
		}

		if securityReport, ok := server["security_report"].(map[string]interface{}); ok && securityReport != nil {
			serverInfo["security_report"] = securityReport
		}

		serverList = append(serverList, serverInfo)
	}

	c.JSON(http.StatusOK, models.ServerResponse{
		Status:  "success",
		Total:   len(serverList),
		Servers: serverList,
	})
}

func createServer(c *gin.Context) {
	var req models.CreateServerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"status": "error",
			"detail": "Invalid request: " + err.Error(),
		})
		return
	}

	bucketName := os.Getenv("S3_BUCKET_NAME")

	existing, err := callPythonS3("get_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": req.Name,
	})
	if err == nil && existing["data"] != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"status": "error",
			"detail": "Server '" + req.Name + "' already exists",
		})
		return
	}

	newServer := map[string]interface{}{
		"name":        req.Name,
		"version":     req.Version,
		"description": req.Description,
		"author":      req.Author,
		"lang":        req.Lang,
		"license":     req.License,
		"entrypoint":  req.Entrypoint,
		"repository": map[string]interface{}{
			"type": req.Repository.Type,
			"url":  req.Repository.URL,
		},
		"pricing": map[string]interface{}{
			"currency": req.Pricing.Currency,
			"amount":   req.Pricing.Amount,
		},
		"meta": map[string]interface{}{
			"created_at": time.Now().UTC().Format(time.RFC3339),
			"updated_at": time.Now().UTC().Format(time.RFC3339),
		},
	}

	if req.Tools != nil {
		newServer["tools"] = *req.Tools
	}

	_, err = callPythonS3("upsert_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": req.Name,
		"server_data": newServer,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status": "error",
			"detail": "Error creating server: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusCreated, models.ServerResponse{
		Status:  "success",
		Message: "Server created",
		Server:  newServer,
	})
}

func updateServer(c *gin.Context) {
	serverName := c.Param("server_name")
	bucketName := os.Getenv("S3_BUCKET_NAME")

	var req models.UpdateServerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"status": "error",
			"detail": "Invalid request: " + err.Error(),
		})
		return
	}

	existingResult, err := callPythonS3("get_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": serverName,
	})
	if err != nil || existingResult["data"] == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"status": "error",
			"detail": "Server '" + serverName + "' not found",
		})
		return
	}

	existing := existingResult["data"].(map[string]interface{})
	updatedData := make(map[string]interface{})
	for k, v := range existing {
		updatedData[k] = v
	}

	newName := serverName
	if req.Name != nil && *req.Name != serverName {
		checkResult, _ := callPythonS3("get_server", map[string]interface{}{
			"bucket_name": bucketName,
			"server_name": *req.Name,
		})
		if checkResult["data"] != nil {
			c.JSON(http.StatusBadRequest, gin.H{
				"status": "error",
				"detail": "Server '" + *req.Name + "' already exists",
			})
			return
		}
		newName = *req.Name
		updatedData["name"] = *req.Name
	}

	if req.Version != nil {
		updatedData["version"] = *req.Version
	}
	if req.Description != nil {
		updatedData["description"] = *req.Description
	}
	if req.Author != nil {
		updatedData["author"] = *req.Author
	}
	if req.Lang != nil {
		updatedData["lang"] = *req.Lang
	}
	if req.License != nil {
		updatedData["license"] = *req.License
	}
	if req.Entrypoint != nil {
		updatedData["entrypoint"] = *req.Entrypoint
	}
	if req.Repository != nil {
		updatedData["repository"] = map[string]interface{}{
			"type": req.Repository.Type,
			"url":  req.Repository.URL,
		}
	}
	if req.Pricing != nil {
		updatedData["pricing"] = map[string]interface{}{
			"currency": req.Pricing.Currency,
			"amount":   req.Pricing.Amount,
		}
	}
	if req.Tools != nil {
		updatedData["tools"] = *req.Tools
	}
	if req.SecurityReport != nil {
		updatedData["security_report"] = *req.SecurityReport
	}

	if meta, ok := updatedData["meta"].(map[string]interface{}); ok {
		if createdAt, exists := meta["created_at"]; exists {
			updatedData["meta"] = map[string]interface{}{
				"created_at": createdAt,
				"updated_at": time.Now().UTC().Format(time.RFC3339),
			}
		} else {
			updatedData["meta"] = map[string]interface{}{
				"updated_at": time.Now().UTC().Format(time.RFC3339),
			}
		}
	} else {
		updatedData["meta"] = map[string]interface{}{
			"updated_at": time.Now().UTC().Format(time.RFC3339),
		}
	}

	if newName != serverName {
		callPythonS3("delete_server", map[string]interface{}{
			"bucket_name": bucketName,
			"server_name": serverName,
		})
	}

	_, err = callPythonS3("upsert_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": newName,
		"server_data": updatedData,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status": "error",
			"detail": "Error updating server: " + err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, models.ServerResponse{
		Status:  "success",
		Message: "Server '" + serverName + "' updated successfully",
		Server:  updatedData,
	})
}

func deleteServer(c *gin.Context) {
	serverName := c.Param("server_name")
	bucketName := os.Getenv("S3_BUCKET_NAME")

	existing, err := callPythonS3("get_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": serverName,
	})
	if err != nil || existing["data"] == nil {
		c.JSON(http.StatusNotFound, gin.H{
			"status": "error",
			"detail": "Server '" + serverName + "' not found",
		})
		return
	}

	_, err = callPythonS3("delete_server", map[string]interface{}{
		"bucket_name": bucketName,
		"server_name": serverName,
	})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status": "error",
			"detail": "Failed to delete server '" + serverName + "'",
		})
		return
	}

	c.JSON(http.StatusOK, models.ServerResponse{
		Status:  "success",
		Message: "Server '" + serverName + "' deleted successfully",
	})
}
