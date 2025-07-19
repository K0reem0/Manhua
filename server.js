const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Proxy endpoint for MangaDex API
app.get('/api/manga', async (req, res) => {
  try {
    const { offset = 0, limit = 100, ...queryParams } = req.query;
    
    // Construct MangaDex API URL
    const url = 'https://api.mangadex.org/manga';
    
    // Forward the request to MangaDex
    const response = await axios.get(url, {
      params: {
        ...queryParams,
        offset,
        limit,
        'order[followedCount]': 'desc',
        'includes[]': 'cover_art',
        'hasAvailableChapters': 'true'
      }
    });
    
    res.json(response.data);
  } catch (error) {
    console.error('Proxy error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Aggregate endpoint
app.get('/api/manga/:id/aggregate', async (req, res) => {
  try {
    const { id } = req.params;
    const response = await axios.get(`https://api.mangadex.org/manga/${id}/aggregate`, {
      params: {
        translatedLanguage: ['en']
      }
    });
    res.json(response.data);
  } catch (error) {
    console.error('Aggregate error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
