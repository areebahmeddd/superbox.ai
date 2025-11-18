package models

// Authentication Request Types
type AuthDeviceStartRequest struct {
	Provider string `json:"provider"`
}

type AuthDevicePollRequest struct {
	DeviceCode string `json:"device_code"`
}

type AuthRegisterRequest struct {
	Email       string  `json:"email"`
	Password    string  `json:"password"`
	DisplayName *string `json:"display_name,omitempty"`
}

type AuthLoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type AuthProviderRequest struct {
	Provider    string  `json:"provider"`
	IDToken     *string `json:"id_token,omitempty"`
	AccessToken *string `json:"access_token,omitempty"`
}

type AuthRefreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

type AuthUpdateRequest struct {
	DisplayName *string `json:"display_name,omitempty"`
	Password    *string `json:"password,omitempty"`
}

// Authentication Response Types
type AuthResponse struct {
	IDToken      string  `json:"id_token"`
	RefreshToken string  `json:"refresh_token"`
	ExpiresIn    int     `json:"expires_in"`
	Email        *string `json:"email,omitempty"`
	LocalID      *string `json:"local_id,omitempty"`
}

type AuthUserProfile struct {
	Email         *string `json:"email,omitempty"`
	LocalID       string  `json:"local_id"`
	DisplayName   *string `json:"display_name,omitempty"`
	EmailVerified bool    `json:"email_verified"`
	Disabled      bool    `json:"disabled"`
}

// Device Session Type
type DeviceSession struct {
	DeviceCode         string
	UserCode           string
	NormalizedUserCode string
	Provider           string
	State              string
	Status             string
	CreatedAt          float64
	ExpiresAt          float64
	CompletedAt        float64
	Tokens             map[string]interface{}
	Error              string
	LastTouched        float64
}

// Server Types
type Repository struct {
	Type string `json:"type"`
	URL  string `json:"url"`
}

type Pricing struct {
	Currency string  `json:"currency"`
	Amount   float64 `json:"amount"`
}

type CreateServerRequest struct {
	Name        string                  `json:"name"`
	Version     string                  `json:"version"`
	Description string                  `json:"description"`
	Author      string                  `json:"author"`
	Lang        string                  `json:"lang"`
	License     string                  `json:"license"`
	Entrypoint  string                  `json:"entrypoint"`
	Repository  Repository              `json:"repository"`
	Pricing     Pricing                 `json:"pricing"`
	Tools       *map[string]interface{} `json:"tools,omitempty"`
}

type UpdateServerRequest struct {
	Name           *string                 `json:"name,omitempty"`
	Version        *string                 `json:"version,omitempty"`
	Description    *string                 `json:"description,omitempty"`
	Author         *string                 `json:"author,omitempty"`
	Lang           *string                 `json:"lang,omitempty"`
	License        *string                 `json:"license,omitempty"`
	Entrypoint     *string                 `json:"entrypoint,omitempty"`
	Repository     *Repository             `json:"repository,omitempty"`
	Pricing        *Pricing                `json:"pricing,omitempty"`
	Tools          *map[string]interface{} `json:"tools,omitempty"`
	SecurityReport *map[string]interface{} `json:"security_report,omitempty"`
}

type ServerResponse struct {
	Status  string        `json:"status"`
	Message string        `json:"message,omitempty"`
	Server  interface{}   `json:"server,omitempty"`
	Total   int           `json:"total,omitempty"`
	Servers []interface{} `json:"servers,omitempty"`
}

// Payment Types
type CreateOrderRequest struct {
	ServerName string  `json:"server_name"`
	Amount     float64 `json:"amount"`
	Currency   string  `json:"currency"`
}

type VerifyPaymentRequest struct {
	RazorpayOrderID   string `json:"razorpay_order_id"`
	RazorpayPaymentID string `json:"razorpay_payment_id"`
	RazorpaySignature string `json:"razorpay_signature"`
	ServerName        string `json:"server_name"`
}

type OrderResponse struct {
	Status string      `json:"status"`
	Order  interface{} `json:"order,omitempty"`
	KeyID  string      `json:"key_id,omitempty"`
	Detail string      `json:"detail,omitempty"`
}

type PaymentResponse struct {
	Status  string      `json:"status"`
	Message string      `json:"message,omitempty"`
	Payment interface{} `json:"payment,omitempty"`
	Detail  string      `json:"detail,omitempty"`
}
