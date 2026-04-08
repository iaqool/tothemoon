import { createClient } from '@supabase/supabase-js';

// Vercel environment variables
const SUPABASE_URL = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.VITE_SUPABASE_KEY || process.env.SUPABASE_KEY;
const RESEND_WEBHOOK_SECRET = process.env.RESEND_WEBHOOK_SECRET;

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

function extractEmail(fromString) {
    if (!fromString) return null;
    const match = fromString.match(/<([^>]+)>/);
    const email = match ? match[1] : fromString;
    return email.trim().toLowerCase();
}

export default async function handler(req, res) {
    // Only allow POST requests
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    // Verify webhook secret
    if (!RESEND_WEBHOOK_SECRET) {
        console.error("[ERROR] RESEND_WEBHOOK_SECRET not configured");
        return res.status(500).json({ error: 'Server misconfiguration' });
    }
    
    const authHeader = req.headers['authorization'];
    if (authHeader !== `Bearer ${RESEND_WEBHOOK_SECRET}`) {
        console.error("[ERROR] Unauthorized webhook request");
        return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
        const payload = req.body;
        
        // Handle Resend Webhook wrapping (if any) or direct raw payload
        const emailData = payload.type && payload.data ? payload.data : payload;
        
        // Validate payload structure
        if (!emailData || typeof emailData !== 'object') {
            return res.status(400).json({ error: 'Invalid payload structure' });
        }
        
        const fromString = emailData.from || '';
        const senderEmail = extractEmail(fromString);
        
        if (!senderEmail) {
            return res.status(400).json({ error: 'Missing from address' });
        }

        console.log(`[INBOUND] Received email from: ${senderEmail}`);

        // 1. Find contact in Supabase
        const { data: contacts, error: contactError } = await supabase
            .from('contacts')
            .select('id, project_id')
            .eq('platform', 'Email')
            .eq('value', senderEmail);
            
        if (contactError) {
            console.error('[ERROR] Supabase contact search failed:', contactError);
            return res.status(500).json({ error: 'DB Error' });
        }

        if (!contacts || contacts.length === 0) {
            console.log(`[INBOUND] Unrecognized sender: ${senderEmail}. Ignoring.`);
            return res.status(200).json({ message: 'Ignored: not a lead' });
        }

        // We assume they replied from one of the matches (if multiple). 
        // We update all matched projects.
        for (const contact of contacts) {
            console.log(`[INBOUND] Matched project_id: ${contact.project_id}`);
            
            // 2. Update project status to 'replied'
            await supabase
                .from('projects')
                .update({ status: 'replied' })
                .eq('id', contact.project_id);
                
            // 3. Log the response in outreach_logs
            await supabase
                .from('outreach_logs')
                .insert({
                    contact_id: contact.id,
                    stage: 'Inbound Reply',
                    response: emailData.text || emailData.html || 'No content parsed',
                    raw_payload: payload 
                });
        }

        return res.status(200).json({ success: true, matchedContacts: contacts.length });

    } catch (error) {
        console.error('[INBOUND ERROR]', error);
        return res.status(500).json({ error: 'Internal Server Error' });
    }
}
