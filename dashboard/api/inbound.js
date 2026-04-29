import { createClient } from '@supabase/supabase-js';
import crypto from 'crypto';

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

function timingSafeEqual(a, b) {
    if (typeof a !== 'string' || typeof b !== 'string') return false;
    const bufA = Buffer.from(a);
    const bufB = Buffer.from(b);
    if (bufA.length !== bufB.length) {
        crypto.timingSafeEqual(bufA, Buffer.alloc(bufA.length));
        return false;
    }
    return crypto.timingSafeEqual(bufA, bufB);
}

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    // --- Request size guard ---
    const rawBody = JSON.stringify(req.body || {});
    if (rawBody.length > 65536) {
        return res.status(413).json({ error: 'Payload too large' });
    }

    if (!RESEND_WEBHOOK_SECRET) {
        return res.status(500).json({ error: 'Server misconfiguration' });
    }
    
    const authHeader = req.headers['authorization'];
    if (!timingSafeEqual(authHeader || '', `Bearer ${RESEND_WEBHOOK_SECRET}`)) {
        return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
        const payload = req.body;
        
        const emailData = payload.type && payload.data ? payload.data : payload;
        
        if (!emailData || typeof emailData !== 'object') {
            return res.status(400).json({ error: 'Invalid payload structure' });
        }
        
        const fromString = emailData.from || '';
        const senderEmail = extractEmail(fromString);
        
        if (!senderEmail) {
            return res.status(400).json({ error: 'Missing from address' });
        }

        // Validate email format
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(senderEmail)) {
            return res.status(400).json({ error: 'Invalid email format' });
        }

        const { data: contacts, error: contactError } = await supabase
            .from('contacts')
            .select('id, project_id')
            .eq('platform', 'Email')
            .eq('value', senderEmail);
            
        if (contactError) {
            console.error('[INBOUND] DB query failed');
            return res.status(500).json({ error: 'DB Error' });
        }

        if (!contacts || contacts.length === 0) {
            return res.status(200).json({ message: 'Ignored: not a lead' });
        }

        for (const contact of contacts) {
            await supabase
                .from('projects')
                .update({ status: 'replied' })
                .eq('id', contact.project_id);
                
            await supabase
                .from('outreach_logs')
                .insert({
                    contact_id: contact.id,
                    stage: 'Inbound Reply',
                    response: (emailData.text || '').slice(0, 5000),
                    raw_payload: null
                });
        }

        return res.status(200).json({ success: true, matchedContacts: contacts.length });

    } catch (error) {
        console.error('[INBOUND] Processing error');
        return res.status(500).json({ error: 'Internal Server Error' });
    }
}
