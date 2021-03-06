from MyCapytain.resources.prototypes.cts.inventory import CtsTextInventoryCollection, CtsTextInventoryMetadata
from MyCapytain.resolvers.utils import CollectionDispatcher

general_collection = CtsTextInventoryCollection()
nt = CtsTextInventoryMetadata('new_testament', parent=general_collection)
nt.set_label('Neues Testament', 'ger')
nt.set_label('New Testament', 'eng')
jewish = CtsTextInventoryMetadata('jewish_texts', parent=general_collection)
jewish.set_label('Jüdische Texte', 'ger')
jewish.set_label('Jewish Texts', 'eng')
comm = CtsTextInventoryMetadata('commentaries', parent=general_collection)
comm.set_label('Kommentare', 'ger')
comm.set_label('Commentaries', 'eng')
organizer = CollectionDispatcher(general_collection, default_inventory_name='jewish_texts')

@organizer.inventory("new_testament")
def organize_formulae(collection, path=None, **kwargs):
    if collection.id.startswith('urn:cts:cjhnt:nt'):
        return True
    return False

@organizer.inventory("commentaries")
def organize_elexicon(collection, path=None, **kwargs):
    if collection.id.startswith('urn:cts:cjhnt:commentary'):
        return True
    return False
