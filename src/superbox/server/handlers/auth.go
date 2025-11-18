package handlers

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"superbox/server/models"

	"github.com/gin-gonic/gin"
)

var (
	deviceSessions = make(map[string]*models.DeviceSession)
	stateIndex     = make(map[string]string)
	userIndex      = make(map[string]string)
	sessionMutex   sync.RWMutex
)

const (
	deviceSessionTTL   = 600
	devicePollInterval = 5
	identityBaseURL    = "https://identitytoolkit.googleapis.com/v1"
	secureTokenURL     = "https://securetoken.googleapis.com/v1/token"
)

var (
	firebaseAPIKey     string
	googleClientID     string
	googleClientSecret string
	githubClientID     string
	githubClientSecret string
	authTemplate       *template.Template
)

func init() {
	firebaseAPIKey = os.Getenv("FIREBASE_API_KEY")
	googleClientID = os.Getenv("GOOGLE_CLIENT_ID")
	googleClientSecret = os.Getenv("GOOGLE_CLIENT_SECRET")
	githubClientID = os.Getenv("GITHUB_CLIENT_ID")
	githubClientSecret = os.Getenv("GITHUB_CLIENT_SECRET")

	templatePath := filepath.Join("src", "superbox", "server", "templates", "auth.html")
	tmpl, err := template.ParseFiles(templatePath)
	if err == nil {
		authTemplate = tmpl
	}
}

func RegisterAuth(api *gin.RouterGroup) {
	auth := api.Group("/auth")
	{
		auth.POST("/device/start", deviceStart)
		auth.POST("/device/poll", devicePoll)
		auth.GET("/device", deviceForm)
		auth.POST("/device", deviceSubmit)
		auth.GET("/device/callback/google", callbackGoogle)
		auth.GET("/device/callback/github", callbackGitHub)

		auth.POST("/register", registerUser)
		auth.POST("/login", loginUser)
		auth.POST("/login/provider", loginProvider)
		auth.POST("/refresh", refreshToken)
		auth.GET("/me", getProfile)
		auth.PATCH("/me", updateProfile)
		auth.DELETE("/me", deleteProfile)
	}
}

func generateDeviceCode() string {
	b := make([]byte, 40)
	rand.Read(b)
	return base64.URLEncoding.EncodeToString(b)
}

func generateUserCode() string {
	alphabet := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	b := make([]byte, 8)
	rand.Read(b)
	raw := ""
	for _, v := range b {
		raw += string(alphabet[int(v)%len(alphabet)])
	}
	return fmt.Sprintf("%s-%s", raw[:4], raw[4:])
}

func normalizeCode(code string) string {
	return strings.ToUpper(strings.ReplaceAll(strings.ReplaceAll(code, "-", ""), " ", ""))
}

func sessionCleanup() {
	now := float64(time.Now().Unix())
	expiredCodes := []string{}

	sessionMutex.Lock()
	for deviceCode, session := range deviceSessions {
		status := session.Status
		expiresAt := session.ExpiresAt
		completedAt := session.CompletedAt
		if completedAt == 0 {
			completedAt = expiresAt
		}

		if expiresAt <= now || (status == "complete" || status == "error" || status == "expired") && now-completedAt > 120 {
			expiredCodes = append(expiredCodes, deviceCode)
		}
	}
	sessionMutex.Unlock()

	for _, code := range expiredCodes {
		removeSession(code)
	}
}

func storeSession(session *models.DeviceSession) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	deviceSessions[session.DeviceCode] = session
	userIndex[session.NormalizedUserCode] = session.DeviceCode
	stateIndex[session.State] = session.DeviceCode
}

func removeSession(deviceCode string) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	session, exists := deviceSessions[deviceCode]
	if !exists {
		return
	}

	delete(deviceSessions, deviceCode)
	delete(userIndex, session.NormalizedUserCode)
	delete(stateIndex, session.State)
}

func getSessionCopy(deviceCode string) *models.DeviceSession {
	sessionMutex.RLock()
	defer sessionMutex.RUnlock()
	session, exists := deviceSessions[deviceCode]
	if !exists {
		return nil
	}

	copy := *session
	return &copy
}

func markSession(deviceCode string, status string, message string) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	session, exists := deviceSessions[deviceCode]
	if !exists {
		return
	}

	session.Status = status
	session.CompletedAt = float64(time.Now().Unix())
	if message != "" {
		session.Error = message
	}
	delete(stateIndex, session.State)
}

func setSessionTokens(deviceCode string, tokens map[string]interface{}) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	session, exists := deviceSessions[deviceCode]
	if !exists {
		return
	}

	session.Status = "complete"
	session.Tokens = tokens
	session.CompletedAt = float64(time.Now().Unix())
	delete(stateIndex, session.State)
}

func findState(state string) string {
	sessionMutex.RLock()
	defer sessionMutex.RUnlock()
	return stateIndex[state]
}

func renderDevicePage(c *gin.Context, message string, code string, isError bool, showForm bool) {
	if authTemplate == nil {
		c.HTML(http.StatusOK, "auth.html", gin.H{
			"message":   message,
			"code":      code,
			"error":     isError,
			"show_form": showForm,
		})
		return
	}

	var buf bytes.Buffer
	err := authTemplate.Execute(&buf, map[string]interface{}{
		"message":   message,
		"code":      code,
		"error":     isError,
		"show_form": showForm,
	})
	if err != nil {
		c.String(http.StatusInternalServerError, "Template error")
		return
	}

	c.Data(http.StatusOK, "text/html; charset=utf-8", buf.Bytes())
}

func checkProvider(provider string) error {
	if provider == "google" && (googleClientID == "" || googleClientSecret == "") {
		return fmt.Errorf("google OAuth is not configured on the server")
	}
	if provider == "github" && (githubClientID == "" || githubClientSecret == "") {
		return fmt.Errorf("github OAuth is not configured on the server")
	}
	return nil
}

func identityURL(endpoint string) string {
	return fmt.Sprintf("%s/%s?key=%s", identityBaseURL, endpoint, firebaseAPIKey)
}

func parseFirebaseResponse(resp *http.Response) (map[string]interface{}, error) {
	var data map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, err
	}

	if resp.StatusCode != http.StatusOK {
		errorMsg := "firebase_error"
		if errData, ok := data["error"].(map[string]interface{}); ok {
			if msg, ok := errData["message"].(string); ok {
				errorMsg = msg
			}
		}
		return nil, fmt.Errorf("%s", errorMsg)
	}

	return data, nil
}

func firebaseExchange(postBody string) (map[string]interface{}, error) {
	url := fmt.Sprintf("%s/accounts:signInWithIdp?key=%s", identityBaseURL, firebaseAPIKey)
	payload := map[string]interface{}{
		"postBody":          postBody,
		"requestUri":        "http://localhost",
		"returnSecureToken": true,
	}

	jsonData, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	return parseFirebaseResponse(resp)
}

func parseAuthResponse(data map[string]interface{}) models.AuthResponse {
	expiresIn := 0
	if ei, ok := data["expiresIn"].(float64); ok {
		expiresIn = int(ei)
	} else if ei, ok := data["expires_in"].(float64); ok {
		expiresIn = int(ei)
	}

	var email, localID *string
	if e, ok := data["email"].(string); ok {
		email = &e
	}
	if lid, ok := data["localId"].(string); ok {
		localID = &lid
	} else if uid, ok := data["user_id"].(string); ok {
		localID = &uid
	}

	return models.AuthResponse{
		IDToken:      getString(data, "idToken", "id_token"),
		RefreshToken: getString(data, "refreshToken", "refresh_token"),
		ExpiresIn:    expiresIn,
		Email:        email,
		LocalID:      localID,
	}
}

func parseProfileResponse(data map[string]interface{}) models.AuthUserProfile {
	var email, displayName, localID *string
	if e, ok := data["email"].(string); ok {
		email = &e
	}
	if dn, ok := data["displayName"].(string); ok {
		displayName = &dn
	}
	if lid, ok := data["localId"].(string); ok {
		localID = &lid
	}

	emailVerified := false
	if ev, ok := data["emailVerified"].(bool); ok {
		emailVerified = ev
	}

	disabled := false
	if d, ok := data["disabled"].(bool); ok {
		disabled = d
	}

	return models.AuthUserProfile{
		Email:         email,
		LocalID:       *localID,
		DisplayName:   displayName,
		EmailVerified: emailVerified,
		Disabled:      disabled,
	}
}

func getString(data map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if val, ok := data[key].(string); ok {
			return val
		}
	}
	return ""
}

func extractToken(authHeader string) (string, error) {
	if authHeader == "" {
		return "", fmt.Errorf("missing authorization header")
	}
	if !strings.HasPrefix(strings.ToLower(authHeader), "bearer ") {
		return "", fmt.Errorf("invalid authorization header")
	}
	token := strings.TrimSpace(authHeader[7:])
	if token == "" {
		return "", fmt.Errorf("invalid authorization header")
	}
	return token, nil
}

func deviceStart(c *gin.Context) {
	sessionCleanup()

	var req models.AuthDeviceStartRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	provider := strings.ToLower(req.Provider)
	if provider != "google" && provider != "github" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Unsupported provider"})
		return
	}

	if err := checkProvider(provider); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"detail": err.Error()})
		return
	}

	now := float64(time.Now().Unix())
	deviceCode := generateDeviceCode()
	userCode := generateUserCode()
	normalized := normalizeCode(userCode)
	stateBytes := make([]byte, 32)
	rand.Read(stateBytes)
	state := base64.URLEncoding.EncodeToString(stateBytes)

	session := &models.DeviceSession{
		DeviceCode:         deviceCode,
		UserCode:           userCode,
		NormalizedUserCode: normalized,
		Provider:           provider,
		State:              state,
		Status:             "pending",
		CreatedAt:          now,
		ExpiresAt:          now + deviceSessionTTL,
	}
	storeSession(session)

	scheme := "http"
	if c.GetHeader("X-Forwarded-Proto") == "https" {
		scheme = "https"
	}
	host := c.GetHeader("Host")
	if host == "" {
		host = c.Request.Host
	}

	verificationURI := fmt.Sprintf("%s://%s/api/v1/auth/device", scheme, host)
	verificationURIComplete := fmt.Sprintf("%s?code=%s", verificationURI, url.QueryEscape(userCode))

	c.JSON(http.StatusOK, gin.H{
		"device_code":               deviceCode,
		"user_code":                 userCode,
		"verification_uri":          verificationURI,
		"verification_uri_complete": verificationURIComplete,
		"interval":                  devicePollInterval,
		"expires_in":                deviceSessionTTL,
	})
}

func devicePoll(c *gin.Context) {
	sessionCleanup()

	var req models.AuthDevicePollRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	session := getSessionCopy(req.DeviceCode)
	if session == nil {
		c.JSON(http.StatusNotFound, gin.H{"detail": "Unknown device code"})
		return
	}

	now := float64(time.Now().Unix())
	if session.ExpiresAt <= now && session.Status == "pending" {
		markSession(req.DeviceCode, "expired", "")
		removeSession(req.DeviceCode)
		c.JSON(http.StatusGone, gin.H{"detail": "Device authorization expired"})
		return
	}

	status := session.Status
	if status == "pending" || status == "authorizing" {
		c.JSON(http.StatusAccepted, gin.H{"status": "pending"})
		return
	}

	if status == "complete" {
		tokens := session.Tokens
		removeSession(req.DeviceCode)
		c.JSON(http.StatusOK, tokens)
		return
	}

	if status == "error" {
		message := session.Error
		if message == "" {
			message = "Authorization failed"
		}
		removeSession(req.DeviceCode)
		c.JSON(http.StatusBadRequest, gin.H{"detail": message})
		return
	}

	if status == "expired" {
		removeSession(req.DeviceCode)
		c.JSON(http.StatusGone, gin.H{"detail": "Device authorization expired"})
		return
	}

	removeSession(req.DeviceCode)
	c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid device session state"})
}

func deviceForm(c *gin.Context) {
	message := c.DefaultQuery("message", "Enter the device code shown in your CLI.")
	errorFlag := c.Query("error") == "true"
	code := c.DefaultQuery("code", "")
	renderDevicePage(c, message, code, errorFlag, true)
}

func deviceSubmit(c *gin.Context) {
	code := c.PostForm("code")
	if code == "" {
		renderDevicePage(c, "Device code is required", code, true, true)
		return
	}

	normalized := normalizeCode(code)
	now := float64(time.Now().Unix())

	sessionMutex.Lock()
	deviceCode := userIndex[normalized]
	var session *models.DeviceSession
	if deviceCode != "" {
		session = deviceSessions[deviceCode]
		if session != nil {
			if session.ExpiresAt <= now {
				session.Status = "expired"
			}
			session.LastTouched = now
			if session.Status == "pending" {
				session.Status = "authorizing"
			}
		}
	}
	sessionMutex.Unlock()

	if session == nil || deviceCode == "" {
		renderDevicePage(c, "Invalid or expired device code. Please try again.", code, true, true)
		return
	}

	if session.Status == "expired" {
		removeSession(deviceCode)
		renderDevicePage(c, "Device code has expired. Restart the login from the CLI.", code, true, true)
		return
	}

	if session.Status == "complete" {
		renderDevicePage(c, "This code has already been used. Return to the CLI.", code, true, true)
		return
	}

	scheme := "http"
	if c.GetHeader("X-Forwarded-Proto") == "https" {
		scheme = "https"
	}
	host := c.GetHeader("Host")
	if host == "" {
		host = c.Request.Host
	}

	if session.Provider == "google" {
		if googleClientID == "" || googleClientSecret == "" {
			markSession(deviceCode, "error", "Google OAuth not configured")
			renderDevicePage(c, "Google login is not available. Contact support.", code, true, true)
			return
		}

		callbackURL := fmt.Sprintf("%s://%s/api/v1/auth/device/callback/google", scheme, host)
		params := url.Values{}
		params.Set("client_id", googleClientID)
		params.Set("redirect_uri", callbackURL)
		params.Set("response_type", "code")
		params.Set("scope", "openid email profile")
		params.Set("state", session.State)
		params.Set("access_type", "offline")
		params.Set("prompt", "consent")

		c.Redirect(http.StatusFound, "https://accounts.google.com/o/oauth2/v2/auth?"+params.Encode())
		return
	}

	if session.Provider == "github" {
		if githubClientID == "" || githubClientSecret == "" {
			markSession(deviceCode, "error", "GitHub OAuth not configured")
			renderDevicePage(c, "GitHub login is not available. Contact support.", code, true, true)
			return
		}

		callbackURL := fmt.Sprintf("%s://%s/api/v1/auth/device/callback/github", scheme, host)
		params := url.Values{}
		params.Set("client_id", githubClientID)
		params.Set("redirect_uri", callbackURL)
		params.Set("scope", "read:user user:email")
		params.Set("state", session.State)
		params.Set("allow_signup", "false")

		c.Redirect(http.StatusFound, "https://github.com/login/oauth/authorize?"+params.Encode())
		return
	}

	markSession(deviceCode, "error", "Unsupported provider")
	renderDevicePage(c, "Unsupported provider", code, true, true)
}

func callbackGoogle(c *gin.Context) {
	state := c.Query("state")
	code := c.Query("code")
	errorParam := c.Query("error")

	if state == "" {
		renderDevicePage(c, "Missing state parameter", "", true, false)
		return
	}

	deviceCode := findState(state)
	session := getSessionCopy(deviceCode)
	if deviceCode == "" || session == nil {
		renderDevicePage(c, "Session not found or expired. Return to the CLI and try again.", "", true, false)
		return
	}

	now := float64(time.Now().Unix())
	if session.ExpiresAt <= now {
		markSession(deviceCode, "expired", "")
		removeSession(deviceCode)
		renderDevicePage(c, "Session has expired. Please restart the login from the CLI.", "", true, false)
		return
	}

	if errorParam != "" {
		message, _ := url.QueryUnescape(errorParam)
		markSession(deviceCode, "error", message)
		renderDevicePage(c, "Authorization failed: "+message, "", true, false)
		return
	}

	if code == "" {
		markSession(deviceCode, "error", "Missing authorization code")
		renderDevicePage(c, "Missing authorization code", "", true, false)
		return
	}

	scheme := "http"
	if c.GetHeader("X-Forwarded-Proto") == "https" {
		scheme = "https"
	}
	host := c.GetHeader("Host")
	if host == "" {
		host = c.Request.Host
	}
	callbackURL := fmt.Sprintf("%s://%s/api/v1/auth/device/callback/google", scheme, host)

	tokenData := url.Values{}
	tokenData.Set("code", code)
	tokenData.Set("client_id", googleClientID)
	tokenData.Set("client_secret", googleClientSecret)
	tokenData.Set("redirect_uri", callbackURL)
	tokenData.Set("grant_type", "authorization_code")

	req, _ := http.NewRequest("POST", "https://oauth2.googleapis.com/token", strings.NewReader(tokenData.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		markSession(deviceCode, "error", err.Error())
		renderDevicePage(c, "Failed to contact Google. Please try again.", "", true, false)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorData map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&errorData)
		markSession(deviceCode, "error", "Google authorization failed")
		renderDevicePage(c, "Google authorization failed. Please try again.", "", true, false)
		return
	}

	var tokens map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&tokens)

	idToken, ok := tokens["id_token"].(string)
	if !ok || idToken == "" {
		markSession(deviceCode, "error", "Missing Google ID token")
		renderDevicePage(c, "Google response did not include an ID token", "", true, false)
		return
	}

	postBody := fmt.Sprintf("id_token=%s&providerId=google.com", url.QueryEscape(idToken))
	firebaseData, err := firebaseExchange(postBody)
	if err != nil {
		markSession(deviceCode, "error", err.Error())
		renderDevicePage(c, "Firebase authentication failed", "", true, false)
		return
	}

	authResp := parseAuthResponse(firebaseData)
	authDict := map[string]interface{}{
		"id_token":      authResp.IDToken,
		"refresh_token": authResp.RefreshToken,
		"expires_in":    authResp.ExpiresIn,
		"provider":      "google",
	}
	if authResp.Email != nil {
		authDict["email"] = *authResp.Email
	}
	if authResp.LocalID != nil {
		authDict["local_id"] = *authResp.LocalID
	}

	setSessionTokens(deviceCode, authDict)
	renderDevicePage(c, "Authentication complete. You may return to the CLI to finish logging in.", "", false, false)
}

func callbackGitHub(c *gin.Context) {
	state := c.Query("state")
	code := c.Query("code")
	errorParam := c.Query("error")

	if state == "" {
		renderDevicePage(c, "Missing state parameter", "", true, false)
		return
	}

	deviceCode := findState(state)
	session := getSessionCopy(deviceCode)
	if deviceCode == "" || session == nil {
		renderDevicePage(c, "Session not found or expired. Return to the CLI and try again.", "", true, false)
		return
	}

	now := float64(time.Now().Unix())
	if session.ExpiresAt <= now {
		markSession(deviceCode, "expired", "")
		removeSession(deviceCode)
		renderDevicePage(c, "Session has expired. Please restart the login from the CLI.", "", true, false)
		return
	}

	if errorParam != "" {
		message, _ := url.QueryUnescape(errorParam)
		markSession(deviceCode, "error", message)
		renderDevicePage(c, "Authorization failed: "+message, "", true, false)
		return
	}

	if code == "" {
		markSession(deviceCode, "error", "Missing authorization code")
		renderDevicePage(c, "Missing authorization code", "", true, false)
		return
	}

	scheme := "http"
	if c.GetHeader("X-Forwarded-Proto") == "https" {
		scheme = "https"
	}
	host := c.GetHeader("Host")
	if host == "" {
		host = c.Request.Host
	}
	callbackURL := fmt.Sprintf("%s://%s/api/v1/auth/device/callback/github", scheme, host)

	tokenData := url.Values{}
	tokenData.Set("client_id", githubClientID)
	tokenData.Set("client_secret", githubClientSecret)
	tokenData.Set("code", code)
	tokenData.Set("redirect_uri", callbackURL)
	tokenData.Set("state", state)

	req, _ := http.NewRequest("POST", "https://github.com/login/oauth/access_token", strings.NewReader(tokenData.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		markSession(deviceCode, "error", err.Error())
		renderDevicePage(c, "Failed to contact GitHub. Please try again.", "", true, false)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorData map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&errorData)
		markSession(deviceCode, "error", "GitHub authorization failed")
		renderDevicePage(c, "GitHub authorization failed. Please try again.", "", true, false)
		return
	}

	var tokens map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&tokens)

	accessToken, ok := tokens["access_token"].(string)
	if !ok || accessToken == "" {
		markSession(deviceCode, "error", "Missing GitHub access token")
		renderDevicePage(c, "GitHub response did not include an access token", "", true, false)
		return
	}

	postBody := fmt.Sprintf("access_token=%s&providerId=github.com", url.QueryEscape(accessToken))
	firebaseData, err := firebaseExchange(postBody)
	if err != nil {
		markSession(deviceCode, "error", err.Error())
		renderDevicePage(c, "Firebase authentication failed", "", true, false)
		return
	}

	authResp := parseAuthResponse(firebaseData)
	authDict := map[string]interface{}{
		"id_token":      authResp.IDToken,
		"refresh_token": authResp.RefreshToken,
		"expires_in":    authResp.ExpiresIn,
		"provider":      "github",
	}
	if authResp.Email != nil {
		authDict["email"] = *authResp.Email
	}
	if authResp.LocalID != nil {
		authDict["local_id"] = *authResp.LocalID
	}

	setSessionTokens(deviceCode, authDict)
	renderDevicePage(c, "Authentication complete. You may return to the CLI to finish logging in.", "", false, false)
}

func registerUser(c *gin.Context) {
	var req models.AuthRegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	payload := map[string]interface{}{
		"email":             req.Email,
		"password":          req.Password,
		"returnSecureToken": true,
	}
	if req.DisplayName != nil {
		payload["displayName"] = *req.DisplayName
	}

	jsonData, _ := json.Marshal(payload)
	reqHTTP, _ := http.NewRequest("POST", identityURL("accounts:signUp"), bytes.NewBuffer(jsonData))
	reqHTTP.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	data, err := parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, parseAuthResponse(data))
}

func loginUser(c *gin.Context) {
	var req models.AuthLoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	payload := map[string]interface{}{
		"email":             req.Email,
		"password":          req.Password,
		"returnSecureToken": true,
	}

	jsonData, _ := json.Marshal(payload)
	reqHTTP, _ := http.NewRequest("POST", identityURL("accounts:signInWithPassword"), bytes.NewBuffer(jsonData))
	reqHTTP.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	data, err := parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, parseAuthResponse(data))
}

func loginProvider(c *gin.Context) {
	var req models.AuthProviderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	provider := strings.ToLower(req.Provider)
	var postBody string

	if provider == "google" {
		token := ""
		if req.IDToken != nil {
			token = *req.IDToken
		} else if req.AccessToken != nil {
			token = *req.AccessToken
		}
		if token == "" {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "Missing id_token or access_token for Google login"})
			return
		}
		field := "id_token"
		if req.IDToken == nil {
			field = "access_token"
		}
		postBody = fmt.Sprintf("%s=%s&providerId=google.com", field, url.QueryEscape(token))
	} else if provider == "github" {
		if req.AccessToken == nil {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "Missing access_token for GitHub login"})
			return
		}
		postBody = fmt.Sprintf("access_token=%s&providerId=github.com", url.QueryEscape(*req.AccessToken))
	} else {
		c.JSON(http.StatusBadRequest, gin.H{"detail": fmt.Sprintf("Unsupported provider '%s'", req.Provider)})
		return
	}

	data, err := firebaseExchange(postBody)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, parseAuthResponse(data))
}

func refreshToken(c *gin.Context) {
	var req models.AuthRefreshRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	payload := url.Values{}
	payload.Set("grant_type", "refresh_token")
	payload.Set("refresh_token", req.RefreshToken)

	url := fmt.Sprintf("%s?key=%s", secureTokenURL, firebaseAPIKey)
	reqHTTP, _ := http.NewRequest("POST", url, strings.NewReader(payload.Encode()))
	reqHTTP.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	data, err := parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, parseAuthResponse(data))
}

func getProfile(c *gin.Context) {
	idToken := c.GetHeader("X-ID-Token")
	authHeader := c.GetHeader("Authorization")

	token := idToken
	if token == "" {
		var err error
		token, err = extractToken(authHeader)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": err.Error()})
			return
		}
	}

	payload := map[string]interface{}{"idToken": token}
	jsonData, _ := json.Marshal(payload)
	reqHTTP, _ := http.NewRequest("POST", identityURL("accounts:lookup"), bytes.NewBuffer(jsonData))
	reqHTTP.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	data, err := parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	users, ok := data["users"].([]interface{})
	if !ok || len(users) == 0 {
		c.JSON(http.StatusNotFound, gin.H{"detail": "User not found"})
		return
	}

	userData, ok := users[0].(map[string]interface{})
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"detail": "User not found"})
		return
	}

	c.JSON(http.StatusOK, parseProfileResponse(userData))
}

func updateProfile(c *gin.Context) {
	authHeader := c.GetHeader("Authorization")
	token, err := extractToken(authHeader)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"detail": err.Error()})
		return
	}

	var req models.AuthUpdateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "Invalid request"})
		return
	}

	payload := map[string]interface{}{
		"idToken":           token,
		"returnSecureToken": true,
	}
	if req.DisplayName != nil {
		payload["displayName"] = *req.DisplayName
	}
	if req.Password != nil {
		payload["password"] = *req.Password
	}

	jsonData, _ := json.Marshal(payload)
	reqHTTP, _ := http.NewRequest("POST", identityURL("accounts:update"), bytes.NewBuffer(jsonData))
	reqHTTP.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	data, err := parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, parseProfileResponse(data))
}

func deleteProfile(c *gin.Context) {
	authHeader := c.GetHeader("Authorization")
	token, err := extractToken(authHeader)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"detail": err.Error()})
		return
	}

	payload := map[string]interface{}{"idToken": token}
	jsonData, _ := json.Marshal(payload)
	reqHTTP, _ := http.NewRequest("POST", identityURL("accounts:delete"), bytes.NewBuffer(jsonData))
	reqHTTP.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(reqHTTP)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	_, err = parseFirebaseResponse(resp)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  "success",
		"message": "Account deleted successfully",
	})
}
