'use server';
/**
 * @fileOverview An AI agent that translates natural language questions into structured search queries for a knowledge graph.
 *
 * - naturalLanguageKnowledgeGraphSearch - A function that interprets a natural language query and generates a structured search query.
 * - NaturalLanguageQueryInput - The input type for the naturalLanguageKnowledgeGraphSearch function.
 * - KnowledgeGraphQueryOutput - The return type for the naturalLanguageKnowledgeGraphSearch function.
 */

import {ai} from '@/ai/genkit';
import {z} from 'genkit';

const NaturalLanguageQueryInputSchema = z.object({
  query: z
    .string()
    .describe(
      'The natural language question about the knowledge graph (e.g., "Show me projects related to renewable energy in Europe seeking funding over $1M" or "Find experts in AI from top universities in the US").'
    ),
});
export type NaturalLanguageQueryInput = z.infer<
  typeof NaturalLanguageQueryInputSchema
>;

const KnowledgeGraphQueryOutputSchema = z.object({
  entityType: z
    .union([
      z.literal('projects'),
      z.literal('experts'),
      z.literal('enterprises'),
      z.literal('funders'),
      z.literal('any'),
    ])
    .describe(
      'The type of entity to search for. Can be "projects", "experts", "enterprises", "funders", or "any" if not specified.'
    ),
  keywords: z
    .array(z.string())
    .optional()
    .describe('A list of keywords or topics to search for.'),
  location: z
    .string()
    .optional()
    .describe(
      'Geographical location filter (e.g., "Europe", "US", "New York").'
    ),
  minFunding: z
    .number()
    .optional()
    .describe('Minimum funding amount in USD (for projects or funders).'),
  maxFunding: z
    .number()
    .optional()
    .describe('Maximum funding amount in USD (for projects or funders).'),
  specificCriteria: z
    .record(z.string(), z.string())
    .optional()
    .describe(
      'Additional key-value criteria that are not covered by other fields (e.g., "affiliation": "top universities", "industry": "healthcare").'
    ),
});
export type KnowledgeGraphQueryOutput = z.infer<
  typeof KnowledgeGraphQueryOutputSchema
>;

export async function naturalLanguageKnowledgeGraphSearch(
  input: NaturalLanguageQueryInput
): Promise<KnowledgeGraphQueryOutput> {
  return naturalLanguageKnowledgeGraphSearchFlow(input);
}

const queryPrompt = ai.definePrompt({
  name: 'knowledgeGraphQueryPrompt',
  input: {schema: NaturalLanguageQueryInputSchema},
  output: {schema: KnowledgeGraphQueryOutputSchema},
  prompt: `You are an AI assistant that translates natural language questions into structured JSON queries for a knowledge graph.

Here are some examples:

User Question: Show me projects related to renewable energy in Europe seeking funding over $1M
JSON Query: {"entityType": "projects", "keywords": ["renewable energy"], "location": "Europe", "minFunding": 1000000}

User Question: Find experts in AI from top universities in the US
JSON Query: {"entityType": "experts", "keywords": ["AI"], "location": "US", "specificCriteria": {"affiliation": "top universities"}}

User Question: Enterprises in tech based in California
JSON Query: {"entityType": "enterprises", "keywords": ["tech"], "location": "California"}

User Question: Funders interested in healthcare startups
JSON Query: {"entityType": "funders", "keywords": ["healthcare startups"]}

User Question: Any entities related to sustainable agriculture
JSON Query: {"entityType": "any", "keywords": ["sustainable agriculture"]}

Strictly adhere to the output JSON schema and accurately extract all relevant information from the user's question. If a numerical value for funding is mentioned with a currency symbol like '$', convert it to a plain number. If a minimum or maximum funding is not explicitly stated, omit the field. If no specific entity type is mentioned, default to "any".

User Question: {{{query}}}
JSON Query: `,
});

const naturalLanguageKnowledgeGraphSearchFlow = ai.defineFlow(
  {
    name: 'naturalLanguageKnowledgeGraphSearchFlow',
    inputSchema: NaturalLanguageQueryInputSchema,
    outputSchema: KnowledgeGraphQueryOutputSchema,
  },
  async (input) => {
    const {output} = await queryPrompt(input);
    return output!;
  }
);
