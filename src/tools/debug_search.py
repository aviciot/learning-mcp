"""Debug VDB search return type."""
import sys
import asyncio
sys.path.insert(0, 'src')

from learning_mcp.vdb import VDB
from learning_mcp.config import get_profile
from learning_mcp.embeddings import Embedder, EmbeddingConfig

async def main():
    prof = get_profile('informatica-cloud')
    vdb = VDB(url='http://vector-db:6333', collection='informatica-cloud', dim=384, distance='cosine')
    
    ecfg = EmbeddingConfig.from_profile(prof)
    embedder = Embedder(ecfg)
    
    vecs = await embedder.embed(['test'])
    results = vdb.search(query_vec=vecs[0], top_k=1)
    
    print(f'Type of results: {type(results)}')
    print(f'Has __len__: {hasattr(results, "__len__")}')
    
    if hasattr(results, '__len__'):
        print(f'Length: {len(results)}')
    
    if results:
        first = results[0]
        print(f'\nType of first item: {type(first)}')
        attrs = [a for a in dir(first) if not a.startswith('_')]
        print(f'Attributes: {attrs[:10]}')  # First 10
        
        # Check if it has payload
        if hasattr(first, 'payload'):
            print(f'\nHas payload attribute: YES')
            print(f'Payload type: {type(first.payload)}')
        else:
            print(f'\nHas payload attribute: NO')
            
        # Check if it's a tuple
        if isinstance(first, tuple):
            print(f'\nIs tuple: YES, length: {len(first)}')
            for i, item in enumerate(first):
                print(f'  Item {i}: type={type(item)}')
    
    await embedder.close()

if __name__ == '__main__':
    asyncio.run(main())
