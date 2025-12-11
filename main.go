Moein, [12/11/2025 2:13 PM]
package main

import (
 "bufio"
 "context"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "golang.org/x/net/proxy"
 "io"
 "log"
 "net"
 "net/http"
 "os"
 "os/exec"
 "path/filepath"
 "strings"
 "sync"
 "time"
)

const (
 DefaultTorrc = "/etc/tor/torrc"
 BackupDir    = "/var/backups"
 Version      = "v1.0-mojenx"
)

var asciiLogo = 
  __  __            _                 
 |  \/  | ___  _ __| | ___  _   _ ___ 
 | |\/| |/ _ \| '__| |/ _ \| | | / __|
 | |  | | (_) | |  | | (_) | |_| \__ \
 |_|  |_|\___/|_|  |_|\___/ \__,_|___/
       mojenX - tor helper  + Version + 


var (
 apiToken   string
 torrcPath  string
 listenAddr string
 logger     = log.New(os.Stdout, "mojenX: ", log.LstdFlags)
 lock       sync.Mutex
)

type response struct {
 OK   bool        json:"ok"
 Msg  string      json:"msg,omitempty"
 Data interface{} json:"data,omitempty"
}

func main() {
 flag.StringVar(&torrcPath, "torrc", DefaultTorrc, "path to torrc")
 flag.StringVar(&listenAddr, "listen", "", "http listen address (empty = interactive CLI)")
 flag.StringVar(&apiToken, "token", "", "api token (or MOJENX_TOKEN env)")
 flag.Parse()

 if apiToken == "" {
  apiToken = os.Getenv("MOJENX_TOKEN")
 }

 fmt.Println(asciiLogo)

 if listenAddr == "" {
  interactiveMenu()
  return
 }

 if apiToken == "" {
  logger.Fatal("API token required for HTTP mode. Provide -token or set MOJENX_TOKEN env")
 }

 mux := http.NewServeMux()
 mux.HandleFunc("/api/v1/status", auth(statusHandler))
 mux.HandleFunc("/api/v1/get-ip", auth(getIPHandler))
 mux.HandleFunc("/api/v1/set-port", auth(setPortHandler))
 mux.HandleFunc("/api/v1/set-countries", auth(setCountriesHandler))
 mux.HandleFunc("/api/v1/restart", auth(restartHandler))
 mux.HandleFunc("/api/v1/reload", auth(reloadHandler))
 mux.HandleFunc("/api/v1/read", auth(readHandler))

 srv := &http.Server{
  Addr:    listenAddr,
  Handler: logRequest(mux),
 }
 logger.Printf("API mode: listening on %s\n", listenAddr)
 if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
  logger.Fatalf("HTTP server error: %v", err)
 }
}

func interactiveMenu() {
 reader := bufio.NewReader(os.Stdin)
 for {
  fmt.Println()
  fmt.Println("mojenX interactive menu")
  fmt.Println("------------------------")
  fmt.Println("1) Show status")
  fmt.Println("2) Set SocksPort")
  fmt.Println("3) Set ExitCountries")
  fmt.Println("4) Reload Tor")
  fmt.Println("5) Restart Tor")
  fmt.Println("6) Get Tor IP")
  fmt.Println("0) Exit")
  fmt.Print("Choice: ")
  txt, _ := reader.ReadString('\n')
  choice := strings.TrimSpace(txt)
  switch choice {
  case "1":
   printStatus()
  case "2":
   fmt.Print("Enter port: ")
   p, _ := reader.ReadString('\n')
   var port int
   fmt.Sscan(strings.TrimSpace(p), &port)
   if port <= 0 {
    fmt.Println("Invalid port")
    continue
   }
   if !isPortAvailable(port) {
    fmt.Println("Port not available")
    continue
   }
   if err := modifyTorrc(torrcPath, &port, nil); err != nil {
    fmt.Println("Error:", err)
   } else {
    _ = reloadTor()
    fmt.Println("SocksPort set.")
   }
  case "3":
   fmt.Print("Enter codes (comma sep, e.g. tr,de): ")
   c, _ := reader.ReadString('\n')
   codes := strings.TrimSpace(c)
   parts := strings.FieldsFunc(codes, func(r rune) bool { return r == ',' || r == ' ' })
   b := strings.Builder{}
   for _, p := range parts {
    p = strings.ToLower(strings.TrimSpace(p))
    if p == "" {
     continue
    }
    b.WriteString("{" + p + "}")
   }
   s := b.String()
   if s == "" {
    fmt.Println("No valid codes")
    continue
   }
   if err := modifyTorrc(torrcPath, nil, &s); err != nil {
    fmt.Println("Error:", err)
   } else {
    _ = reloadTor()
    fmt.Println("ExitNodes updated.")
   }
  case "4":
   _ = reloadTor()
   fmt.Println("Reloaded.")
  case "5":
   _ = restartTor()
   fmt.Println("Restarted.")
  case "6":
   ip, err := getIPViaTorDefault()
   if err != nil {
    fmt.Println("Error:", err)
   } else {
    fmt.Println("Tor IP:", ip)
   }
  case "0":
   return
  default:
   fmt.Println("Invalid")
  }
 }
}

Moein, [12/11/2025 2:13 PM]
func printStatus() {
 lines, _ := readTorrc(torrcPath)
 fmt.Println("torrc contents:")
 for _, l := range lines {
  fmt.Println("  " + l)
 }
 fmt.Println()
 ip, _ := getIPViaTorDefault()
 fmt.Println("Tor current IP:", ip)
}

func auth(h http.HandlerFunc) http.HandlerFunc {
 return func(w http.ResponseWriter, r *http.Request) {
  token := r.Header.Get("Authorization")
  token = strings.TrimPrefix(token, "Bearer ")

  if token == "" {
   token = r.URL.Query().Get("token")
  }
  if token != apiToken || token == "" {
   writeJSON(w, http.StatusUnauthorized, response{OK: false, Msg: "unauthorized"})
   return
  }
  h(w, r)
 }
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
 w.Header().Set("Content-Type", "application/json")
 w.WriteHeader(code)
 _ = json.NewEncoder(w).Encode(v)
}

func logRequest(next http.Handler) http.Handler {
 return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
  logger.Printf("%s %s from %s\n", r.Method, r.URL.Path, r.RemoteAddr)
  next.ServeHTTP(w, r)
 })
}

func readTorrc(path string) ([]string, error) {
 f, err := os.Open(path)
 if err != nil {
  return nil, err
 }
 defer f.Close()
 var lines []string
 sc := bufio.NewScanner(f)
 for sc.Scan() {
  lines = append(lines, sc.Text())
 }
 return lines, sc.Err()
}

func backupTorrc(path string) {
 if _, err := os.Stat(path); err != nil {
  return
 }
 dst := filepath.Join(BackupDir, "torrc.bak."+time.Now().Format("20060102150405"))
 _ = os.MkdirAll(BackupDir, 0755)
 b, _ := os.ReadFile(path)
 _ = os.WriteFile(dst, b, 0644)
}

func writeTorrc(path string, lines []string) error {
 backupTorrc(path)
 tmp := path + ".tmp"
 f, err := os.Create(tmp)
 if err != nil {
  return err
 }
 for _, l := range lines {
  _, _ = f.WriteString(l + "\n")
 }
 f.Close()
 return os.Rename(tmp, path)
}

func modifyTorrc(path string, socks *int, exitNodes *string) error {
 lock.Lock()
 defer lock.Unlock()

 lines, _ := readTorrc(path)
 var out []string
 changed := false

 for _, l := range lines {
  t := strings.TrimSpace(l)
  if strings.HasPrefix(t, "SocksPort") && socks != nil {
   out = append(out, fmt.Sprintf("SocksPort %d", *socks))
   changed = true
  } else if strings.HasPrefix(t, "ExitNodes") && exitNodes != nil {
   out = append(out, fmt.Sprintf("ExitNodes %s", *exitNodes))
   changed = true
  } else {
   out = append(out, l)
  }
 }
 if !changed {
  if socks != nil {
   out = append(out, fmt.Sprintf("SocksPort %d", *socks))
  }
  if exitNodes != nil {
   out = append(out, fmt.Sprintf("ExitNodes %s", *exitNodes))
  }
 }
 return writeTorrc(path, out)
}

func reloadTor() error {
 return exec.Command("systemctl", "reload", "tor").Run()
}

func restartTor() error {
 return exec.Command("systemctl", "restart", "tor").Run()
}

func isPortAvailable(port int) bool {
 conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), time.Second)
 if err != nil {
  return true
 }
 conn.Close()
 return false
}

func statusHandler(w http.ResponseWriter, r *http.Request) {
 lines, _ := readTorrc(torrcPath)
 writeJSON(w, 200, response{OK: true, Data: strings.Join(lines, "\n")})
}

func readHandler(w http.ResponseWriter, r *http.Request) {
 lines, _ := readTorrc(torrcPath)
 writeJSON(w, 200, response{OK: true, Data: strings.Join(lines, "\n")})
}

func restartHandler(w http.ResponseWriter, r *http.Request) {
 err := restartTor()
 if err != nil {
  writeJSON(w, 500, response{OK: false, Msg: err.Error()})
  return
 }
 writeJSON(w, 200, response{OK: true, Msg: "restarted"})
}

func reloadHandler(w http.ResponseWriter, r *http.Request) {
 err := reloadTor()
 if err != nil {
  writeJSON(w, 500, response{OK: false, Msg: err.Error()})
  return
 }
 writeJSON(w, 200, response{OK: true, Msg: "reloaded"})
}

func setPortHandler(w http.ResponseWriter, r *http.Request) {

Moein, [12/11/2025 2:13 PM]
var body struct{ Port int }
 _ = json.NewDecoder(r.Body).Decode(&body)
 if body.Port <= 0 {
  writeJSON(w, 400, response{OK: false, Msg: "invalid port"})
  return
 }
 if !isPortAvailable(body.Port) {
  writeJSON(w, 400, response{OK: false, Msg: "port not available"})
  return
 }
 _ = modifyTorrc(torrcPath, &body.Port, nil)
 _ = reloadTor()
 writeJSON(w, 200, response{OK: true, Msg: "port updated"})
}

func setCountriesHandler(w http.ResponseWriter, r *http.Request) {
 var body struct{ Codes string }
 _ = json.NewDecoder(r.Body).Decode(&body)
 if strings.TrimSpace(body.Codes) == "" {
  writeJSON(w, 400, response{OK: false, Msg: "invalid codes"})
  return
 }
 parts := strings.FieldsFunc(body.Codes, func(r rune) bool { return r == ',' || r == ' ' })
 b := strings.Builder{}
 for _, p := range parts {
  b.WriteString("{" + strings.TrimSpace(p) + "}")
 }
 s := b.String()
 _ = modifyTorrc(torrcPath, nil, &s)
 _ = reloadTor()
 writeJSON(w, 200, response{OK: true, Msg: "countries updated"})
}

func restartHandler(w http.ResponseWriter, r *http.Request) {
 if err := restartTor(); err != nil {
  writeJSON(w, 500, response{OK: false, Msg: err.Error()})
  return
 }
 writeJSON(w, 200, response{OK: true, Msg: "tor restarted"})
}

func reloadHandler(w http.ResponseWriter, r *http.Request) {
 if err := reloadTor(); err != nil {
  writeJSON(w, 500, response{OK: false, Msg: err.Error()})
  return
 }
 writeJSON(w, 200, response{OK: true, Msg: "tor reloaded"})
}

func getIPHandler(w http.ResponseWriter, r *http.Request) {
 ip, err := getIPViaTorDefault()
 if err != nil {
  writeJSON(w, 500, response{OK: false, Msg: err.Error()})
  return
 }
 writeJSON(w, 200, response{OK: true, Data: ip})
}

func getIPViaTorDefault() (string, error) {
 lines, _ := readTorrc(torrcPath)
 socks := 9050
 for _, l := range lines {
  t := strings.TrimSpace(l)
  if strings.HasPrefix(t, "SocksPort") {
   parts := strings.Fields(t)
   if len(parts) >= 2 {
    fmt.Sscan(parts[1], &socks)
   }
  }
 }
 return getIPViaTor(socks)
}

func getIPViaTor(port int) (string, error) {
 dialer, err := proxy.SOCKS5("tcp", fmt.Sprintf("127.0.0.1:%d", port), nil, proxy.Direct)
 if err != nil {
  return "", err
 }
 conn, err := dialer.Dial("tcp", "checkip.amazonaws.com:80")
 if err != nil {
  return "", err
 }
 defer conn.Close()
 req := "GET / HTTP/1.1\r\nHost: checkip.amazonaws.com\r\nConnection: close\r\n\r\n"
 _, _ = conn.Write([]byte(req))
 buf := make([]byte, 4096)
 n, _ := conn.Read(buf)
 resp := string(buf[:n])
 lines := strings.Split(resp, "\n")
 return strings.TrimSpace(lines[len(lines)-1]), nil
}
