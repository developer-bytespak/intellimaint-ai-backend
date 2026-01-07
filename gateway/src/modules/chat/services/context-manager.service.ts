/**
 * Context Manager Service (Helper 4 + 7: generate_context_summary + update_context_summary)
 *
 * This service manages the conversation context window and generates summaries.
 * It implements a 6-message (3 turn) sliding window strategy: keeping recent
 * user+assistant pairs intact while summarizing older ones to stay within token limits.
 *
 * Architecture:
 * - Window: 6 messages (3 user+assistant pairs), ending on assistant role
 * - Rolling Rewrite: Every turn after 6 messages, incorporate evicted pair into summary
 * - Periodic Recompress: Every 20 messages, tighten summary to prevent drift/bloat
 * - Summarization: Uses gpt-4o-mini with 3x retry, text-only, soft cap ~1000 chars
 *
 * Pipeline Integration:
 * - Stage 4 (before LLM): prepareContext() returns last 6 messages + stored summary
 * - Stage 7 (after LLM): updateContextSummary() performs rolling rewrite or recompress
 *
 * Responsibilities:
 * - Maintain 6-message even sliding context window (preserves user+assistant pairs)
 * - Generate concise text-only summaries using gpt-4o-mini
 * - Prepare context data for LLM calls (summary + recent messages)
 * - Incrementally update stored summaries after each turn
 * - Handle summary generation timing (rolling rewrite per turn, recompress every 20)
 * - Enforce assistant-ended window and exclude stopped/partial messages
 * - Retry summarization up to 3 times with exponential backoff
 *
 * Context Window Logic:
 * - If ≤6 messages: pass all messages, empty summary
 * - If >6 messages: pass last 6 (ending on assistant) + stored summary
 * - Eviction: 2 messages per turn (user+assistant pair) fall outside window
 *
 * Summary Update Strategy:
 * - Rolling rewrite (default, every turn): S_new = summarize(S_old + evicted_pair)
 * - Periodic recompress (every 20 messages): S_new = recompress(S_old)
 * - Retry policy: 3 attempts with exponential backoff; fallback to S_old on failure
 *
 * Team: Teammate 4
 * Your Helper Functions:
 *   - generate_context_summary(prompts_and_responses) (Helper 4)
 *   - update_context_summary(new_summary) (Helper 7)
 */

import { Injectable, Logger, BadRequestException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { ContextData } from '../dto/pipeline-message.dto';
import OpenAI from 'openai';

@Injectable()
export class ContextManagerService {
  private readonly logger = new Logger(ContextManagerService.name);
  // Even-sized window to preserve user+assistant pairs
  private readonly CONTEXT_WINDOW_SIZE = 6;
  private readonly RECOMPRESS_EVERY = 20; // recompress summary every 20 messages
  private readonly MAX_SUMMARY_CHARS = 1000; // soft cap
  private readonly SUMMARY_RETRIES = 3;
  private readonly RETRY_BASE_DELAY_MS = 500;
  private readonly SUMMARIZATION_MODEL = 'gpt-4o-mini';
  private readonly openai: OpenAI;

  constructor(private prisma: PrismaService) {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY environment variable not configured');
    }
    this.openai = new OpenAI({ apiKey });
  }

  /**
   * Prepare context data for LLM call
   *
   * @param sessionId - Chat session ID
   * @param messages - All messages in session
   * @returns Object with summary string and recent messages array
   *
   * Logic:
   * - If <= 5 messages: return all messages and empty summary
   * - If > 5 messages: return last 5 messages + existing/generated summary
   */
  async prepareContext(sessionId: string, messages: any[]): Promise<ContextData> {
    this.logger.debug(
      `Preparing context for session ${sessionId} with ${messages.length} messages`,
    );

    // Exclude stopped/partial messages
    const filtered = (messages || []).filter((m) => !m.isStopped);

    if (filtered.length === 0) {
      return { summary: '', recentMessages: [] };
    }

    // If ≤ window size: return all and empty summary
    if (filtered.length <= this.CONTEXT_WINDOW_SIZE) {
      return { summary: '', recentMessages: filtered };
    }

    // Fetch existing summary from DB
    const session = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      select: { contextSummary: true },
    });
    const summary = session?.contextSummary ?? '';

    // Select last N messages, enforce assistant-ended window and even count
    let lastN = filtered.slice(Math.max(0, filtered.length - this.CONTEXT_WINDOW_SIZE));
    lastN = this.enforceAssistantEndedEvenWindow(lastN);

    return { summary, recentMessages: lastN };
  }

  /**
   * Update context summary after message exchange
   * Generate new summary if message count is multiple of CONTEXT_WINDOW_SIZE
   *
   * @param sessionId - Chat session ID
   * @param userMessage - Latest user message
   * @param assistantMessage - Latest assistant message
   */
  async updateContextSummary(
    sessionId: string,
    userMessage: any,
    assistantMessage: any,
  ): Promise<void> {
    this.logger.debug(`Updating context summary for session ${sessionId}`);
    // Fetch all messages for session, exclude stopped
    const all = await this.prisma.chatMessage.findMany({
      where: { sessionId, isStopped: false },
      orderBy: { createdAt: 'asc' },
      select: { id: true, role: true, content: true, createdAt: true },
    });

    const total = all.length;
    if (total <= this.CONTEXT_WINDOW_SIZE) {
      // No summary needed yet
      return;
    }

    // Get existing summary
    const session = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      select: { contextSummary: true },
    });
    const existingSummary = session?.contextSummary ?? '';

    // Determine last window and evicted messages
    let lastN = all.slice(Math.max(0, total - this.CONTEXT_WINDOW_SIZE));
    lastN = this.enforceAssistantEndedEvenWindow(lastN);
    const evictedCount = Math.max(0, total - lastN.length);
    const evicted = all.slice(Math.max(0, evictedCount - 2), evictedCount); // last 1–2 outside window

    // Choose mode: recompress every 20 messages, else rolling rewrite
    const shouldRecompress = total % this.RECOMPRESS_EVERY === 0;

    let newSummary = existingSummary;
    try {
      if (shouldRecompress) {
        newSummary = await this.generateRecompressSummary(existingSummary);
      } else {
        newSummary = await this.generateRollingSummary(existingSummary, evicted);
      }
    } catch (error) {
      // Retry-once handled inside generate* methods; if still failing, keep old summary silently
      this.logger.warn(`Summary generation failed, keeping existing summary: ${error.message}`);
      return;
    }

    // Persist updated summary
    await this.prisma.chatSession.update({
      where: { id: sessionId },
      data: { contextSummary: newSummary },
    });
  }

  /**
   * Helper: Generate summary of older messages
   * Uses OpenAI API to create concise summary of conversation
   *
   * @param messages - Messages to summarize
   * @returns Concise summary string
   */
  // Rolling rewrite: combine existing summary with evicted pair to produce updated summary
  private async generateRollingSummary(existingSummary: string, evicted: any[]): Promise<string> {
    const formattedEvicted = this.formatMessagesForSummarization(evicted);
    const systemPrompt = `You are a conversation summarizer for a maintenance assistant chatbot. Rewrite the summary below to incorporate the new messages. Keep it concise, text-only, under ${this.MAX_SUMMARY_CHARS} characters. Preserve key questions, answers, and decisions.`;
    const userContent = `Current summary:\n${existingSummary}\n\nNew messages (most recent messages outside the window):\n${formattedEvicted}\n\nRewrite the updated concise summary.`;

    return this.callOpenAISummary(systemPrompt, userContent);
  }

  // Periodic recompress: tighten existing summary to prevent drift and bloat
  private async generateRecompressSummary(existingSummary: string): Promise<string> {
    const systemPrompt = `You are a conversation summarizer for a maintenance assistant chatbot. Tighten the summary below to remove redundancy while preserving meaning. Keep it concise, text-only, under ${this.MAX_SUMMARY_CHARS} characters.`;
    const userContent = `Current summary:\n${existingSummary}\n\nRewrite a more concise version.`;
    return this.callOpenAISummary(systemPrompt, userContent);
  }

  /**
   * Helper: Format messages for summarization
   */
  private formatMessagesForSummarization(messages: any[]): string {
    if (!messages || messages.length === 0) return '(no new messages)';
    return messages
      .map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
      .join('\n');
  }

  /**
   * Helper: Get total message count for session
   */
  private async getMessageCount(sessionId: string): Promise<number> {
    return this.prisma.chatMessage.count({ where: { sessionId, isStopped: false } });
  }

  /**
   * Helper: Get older messages (not in recent window)
   */
  private async getOlderMessages(
    sessionId: string,
    windowSize: number = this.CONTEXT_WINDOW_SIZE,
  ): Promise<any[]> {
    const all = await this.prisma.chatMessage.findMany({
      where: { sessionId, isStopped: false },
      orderBy: { createdAt: 'asc' },
      select: { id: true, role: true, content: true, createdAt: true },
    });
    let lastN = all.slice(Math.max(0, all.length - windowSize));
    lastN = this.enforceAssistantEndedEvenWindow(lastN);
    const evictedCount = Math.max(0, all.length - lastN.length);
    return all.slice(0, evictedCount);
  }

  // Ensure window ends with assistant and has an even number of messages (pairs)
  private enforceAssistantEndedEvenWindow(messages: any[]): any[] {
    let arr = [...(messages || [])];
    // Enforce assistant end
    while (arr.length > 0 && arr[arr.length - 1].role !== 'assistant') {
      arr.pop();
    }
    // Enforce even count (pairs)
    if (arr.length % 2 !== 0 && arr.length > 1) {
      arr = arr.slice(1); // drop the oldest to make count even
    }
    return arr;
  }

  // Call OpenAI to produce summary with retry policy
  private async callOpenAISummary(systemPrompt: string, userContent: string): Promise<string> {
    let lastError: any;
    for (let attempt = 1; attempt <= this.SUMMARY_RETRIES; attempt++) {
      try {
        const response = await this.openai.chat.completions.create({
          model: this.SUMMARIZATION_MODEL,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userContent },
          ],
          max_tokens: 512,
        });
        const text = response.choices?.[0]?.message?.content?.trim() || '';
        if (!text) throw new Error('Empty summary returned');
        if (text.length > this.MAX_SUMMARY_CHARS) {
          this.logger.warn(`Summary length ${text.length} exceeds soft cap ${this.MAX_SUMMARY_CHARS}`);
        }
        return text;
      } catch (error: any) {
        lastError = error;
        const delay = Math.pow(2, attempt - 1) * this.RETRY_BASE_DELAY_MS;
        this.logger.warn(`Summary attempt ${attempt}/${this.SUMMARY_RETRIES} failed: ${error.message}. Retrying in ${delay}ms`);
        if (attempt < this.SUMMARY_RETRIES) {
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
      }
    }
    throw lastError ?? new Error('Summary generation failed');
  }
}
