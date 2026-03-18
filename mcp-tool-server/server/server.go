package server

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	pb "github.com/AvinashSaxena777/papermind/mcp-tool-server/proto"
)

type PaperAnalysisServer struct {
	pb.UnimplementedPaperAnalysisServiceServer
}

func fetchRelatedPapers(paperURL string) []string {
	log.Printf(" [goroutine] Fetching related papers for: %s", paperURL)
	time.Sleep(1 * time.Second)
	return []string{
		"BERT: Pre-training of Deep Bidirectional Transformers",
		"GPT-3: Language Models are Few-Shot Learners",
		"RoBERTa: A Robustly Optimized BERT Pretraining Approach",
	}
}

func parsePdf(paperURL string) string {
	log.Printf(" [goroutine] Parsing pdf content from %s", paperURL)
	time.Sleep(1500 * time.Millisecond)
	return fmt.Sprint(
		"Abstract: This paper presents a novel approach to sequence modeling "+
			"using self-attention mechanisms. The architecture eliminates recurrence "+
			"and convolutions entirely. URL: %s", paperURL,
	)
}

func (s *PaperAnalysisServer) AnalyzePaper(
	ctx context.Context,
	req *pb.AnalyzeRequest,
) (*pb.AnalyzeResponse, error) {

	log.Printf("Received AnalyzePaper request: job_id=%s title=%s", req.JobId, req.PaperTitle)

	var wg sync.WaitGroup

	relatedPapersChan := make(chan []string, 1)
	pdfContentChan := make(chan string, 1)

	wg.Add(1)
	go func() {
		defer wg.Done()
		relatedPapers := fetchRelatedPapers(req.PaperUrl)
		relatedPapersChan <- relatedPapers
	}()

	wg.Add(1)
	go func() {
		defer wg.Done()
		pdfContent := parsePdf(req.PaperUrl)
		pdfContentChan <- pdfContent
	}()

	wg.Wait()

	relatedPapers := <-relatedPapersChan
	pdfContent := <-pdfContentChan

	log.Printf("Both goroutines completed for job_id=%s", req.JobId)
	log.Printf("PDF content length: %d chars", len(pdfContent))
	log.Printf("Related papers found: %d", len(relatedPapers))

	keyFindings := []*pb.KeyFinding{
		{
			Finding:        "Self-attention mechanism replaces recurrence entirely",
			RelevanceScore: 0.95,
		},
		{
			Finding:        fmt.Sprintf("Related to %d recent papers in the field", len(relatedPapers)),
			RelevanceScore: 0.88,
		},
		{
			Finding:        "Parallelizable training significantly faster than RNN/LSTM",
			RelevanceScore: 0.82,
		},
	}

	response := &pb.AnalyzeResponse{
		JobId:  req.JobId,
		Status: "completed",
		Summary: fmt.Sprintf(
			"Analysis of '%s': The paper introduces a novel architecture "+
				"based on self-attention. PDF parsed successfully (%d chars). "+
				"Found %d related papers.",
			req.PaperTitle,
			len(pdfContent),
			len(relatedPapers),
		),
		KeyFindings:     keyFindings,
		ConfidenceScore: 0.87,
		ErrorMessage:    "",
	}

	log.Printf("AnalyzePaper completed for job_id=%s", req.JobId)
	return response, nil
}
