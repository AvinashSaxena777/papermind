package main

import (
	"fmt"
	"log"
	"net"
	"os"

	"google.golang.org/grpc"

	pb "github.com/AvinashSaxena777/papermind/mcp-tool-server/proto"
	"github.com/AvinashSaxena777/papermind/mcp-tool-server/server"
)

func getPort() string {
	port := os.Getenv("GRPC_PORT")
	if port == "" {
		port = "50051" // default if not set
	}
	return ":" + port
}

func main() {

	PORT := getPort()

	listener, err := net.Listen("tcp", PORT)
	if err != nil {
		log.Fatalf("Failed to listen on port %s: %v", PORT, err)
	}

	fmt.Printf("MCP Tool Server listening on port: %s\n", PORT)

	grpcServer := grpc.NewServer()

	pb.RegisterPaperAnalysisServiceServer(
		grpcServer,
		&server.PaperAnalysisServer{},
	)

	fmt.Println("PaperAnalysisService registered")
	fmt.Println("Waiting for grpc calls ")

	if err := grpcServer.Serve(listener); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
