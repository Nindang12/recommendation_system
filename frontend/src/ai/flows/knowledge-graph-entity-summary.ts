'use server';
/**
 * @fileOverview This file implements a Genkit flow for summarizing entities (projects, experts, enterprises, funders) from a knowledge graph.
 *
 * - knowledgeGraphEntitySummary - A function that handles the summarization of a given entity.
 * - KnowledgeGraphEntitySummaryInput - The input type for the knowledgeGraphEntitySummary function.
 * - KnowledgeGraphEntitySummaryOutput - The return type for the knowledgeGraphEntitySummary function.
 */

import {ai} from '@/ai/genkit';
import {z} from 'genkit';

const KnowledgeGraphEntitySummaryInputSchema = z.object({
  entityType: z
    .enum(['project', 'expert', 'enterprise', 'funder'])
    .describe('The type of the entity to summarize.'),
  entityData: z
    .string()
    .describe(
      'Detailed JSON or text data about the entity from the knowledge graph.'
    ),
});
export type KnowledgeGraphEntitySummaryInput = z.infer<
  typeof KnowledgeGraphEntitySummaryInputSchema
>;

const KnowledgeGraphEntitySummaryOutputSchema = z.object({
  summary: z.string().describe('A concise, synthesized summary of the entity.'),
});
export type KnowledgeGraphEntitySummaryOutput = z.infer<
  typeof KnowledgeGraphEntitySummaryOutputSchema
>;

export async function knowledgeGraphEntitySummary(
  input: KnowledgeGraphEntitySummaryInput
): Promise<KnowledgeGraphEntitySummaryOutput> {
  return knowledgeGraphEntitySummaryFlow(input);
}

const summarizeEntityPrompt = ai.definePrompt({
  name: 'summarizeEntityPrompt',
  input: {schema: KnowledgeGraphEntitySummaryInputSchema},
  output: {schema: KnowledgeGraphEntitySummaryOutputSchema},
  prompt: `You are an AI assistant specialized in summarizing knowledge graph entities. Your task is to provide a concise, synthesized summary of the provided {{entityType}} details, focusing on its key attributes, contributions, and connections within the knowledge graph.

The summary should be easy to understand and help a user quickly grasp its relevance and decide if they need to explore further. If the data is not well-structured, try your best to extract relevant information.

Here is the detailed data for the {{entityType}}:
{{{entityData}}}`,
});

const knowledgeGraphEntitySummaryFlow = ai.defineFlow(
  {
    name: 'knowledgeGraphEntitySummaryFlow',
    inputSchema: KnowledgeGraphEntitySummaryInputSchema,
    outputSchema: KnowledgeGraphEntitySummaryOutputSchema,
  },
  async (input) => {
    const {output} = await summarizeEntityPrompt(input);
    return output!;
  }
);
