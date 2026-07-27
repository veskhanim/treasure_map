const { google } = require('googleapis');
const SCOPES = ['https://www.googleapis.com/auth/spreadsheets'];

async function getSheetsService() {
    const credentials = JSON.parse(process.env.GOOGLE_CREDENTIALS);
    const auth = new google.auth.GoogleAuth({
        credentials,
        scopes: SCOPES
    });
    return google.sheets({ version: 'v4', auth });
}

module.exports = async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    try {
        const sheets = await getSheetsService();
        const SHEET_ID = process.env.SHEET_ID;

        if (req.method === 'GET') {
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Videos!A:N'
            });
            
            const rows = response.data.values;
            const videos = rows.slice(1).map(row => ({
                id: row[0],
                title: row[1],
                kr_url: row[2],
                ru_url: row[3],
                en_url: row[4],
                category: row[5],
                members: row[6] ? row[6].split(',') : [],
                date: row[7],
                duration: row[8],
                watchedOriginal: row[9] === 'true',
                watchedRu: row[10] === 'true',
                watchedEn: row[11] === 'true',
                channel_id: row[12],
                added_by: row[13]
            }));
            
            return res.status(200).json(videos);
        }

        if (req.method === 'POST') {
            const v = req.body;
            const row = [
                v.id, v.title, v.kr_url || '', v.ru_url || '', v.en_url || '',
                v.category || 'Interview', (v.members || []).join(','),
                v.date || '', v.duration || '0:00',
                v.watchedOriginal ? 'true' : 'false',
                v.watchedRu ? 'true' : 'false',
                v.watchedEn ? 'true' : 'false',
                v.channel_id || '', v.added_by || 'app'
            ];
            
            await sheets.spreadsheets.values.append({
                spreadsheetId: SHEET_ID,
                range: 'Videos!A:N',
                valueInputOption: 'RAW',
                resource: { values: [row] }
            });
            
            return res.status(200).json({ success: true });
        }

        if (req.method === 'PUT') {
            const { id } = req.query;
            const v = req.body;
            
            const response = await sheets.spreadsheets.values.get({
                spreadsheetId: SHEET_ID,
                range: 'Videos!A:N'
            });
            
            const rows = response.data.values;
            const rowIndex = rows.findIndex(row => row[0] === id);
            
            if (rowIndex === -1) {
                return res.status(404).json({ error: 'Video not found' });
            }
            
            const newRow = [
                id, v.title, v.kr_url || '', v.ru_url || '', v.en_url || '',
                v.category || 'Interview', (v.members || []).join(','),
                v.date || '', v.duration || '0:00',
                v.watchedOriginal ? 'true' : 'false',
                v.watchedRu ? 'true' : 'false',
                v.watchedEn ? 'true' : 'false',
                v.channel_id || '', v.added_by || 'app'
            ];
            
            await sheets.spreadsheets.values.update({
                spreadsheetId: SHEET_ID,
                range: `Videos!A${rowIndex + 1}:N${rowIndex + 1}`,
                valueInputOption: 'RAW',
                resource: { values: [newRow] }
            });
            
            return res.status(200).json({ success: true });
        }
        
        return res.status(405).json({ error: 'Method not allowed' });
    } catch (error) {
        console.error('Error:', error);
        return res.status(500).json({ error: error.message });
    }
};