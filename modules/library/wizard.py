import datetime

from trytond.pool import Pool
from trytond.pyson import Eval, PYSONEncoder
from trytond.transaction import Transaction
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateView, StateTransition, StateAction
from trytond.wizard import Button
from trytond.exceptions import UserWarning, UserError
import web_pdb
__all__ = [
    'CreateExemplaries',
    'CreateExemplariesParameters',
    'FuseBooks',
    'FuseBooksSelectMain',
    'FuseBooksPreview',
    ]


class CreateExemplaries(Wizard):
    'Create Exemplaries'
    __name__ = 'library.book.create_exemplaries'

    start_state = 'parameters'
    parameters = StateView('library.book.create_exemplaries.parameters',
        'library.create_exemplaries_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Créer', 'create_exemplaries', 'tryton-go-next',
                default=True)])
    create_exemplaries = StateTransition()
    open_exemplaries = StateAction('library.act_exemplary')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        """
        cls._error_messages.update({
                'invalid_model': 'This action should be started from a book',
                'invalid_date': 'You cannot purchase books in the future',
                })
        """        

    def default_parameters(self, name):
        if Transaction().context.get('active_model', '') != 'library.book':
            raise UserError('Cette action doit être déclenché du model Livre')
     

        return {
            'acquisition_date': datetime.date.today(),
            'book': Transaction().context.get('active_id'),
            'acquisition_price': 0
    
            }

    def transition_create_exemplaries(self):
        if (self.parameters.acquisition_date and
                self.parameters.acquisition_date > datetime.date.today()):
            raise UserError('On ne peut pas programmer l\'achat d\'un livre ')
        Exemplary = Pool().get('library.book.exemplary')
        to_create = []
        while len(to_create) < self.parameters.number_of_exemplaries:
            exemplary = Exemplary()
            exemplary.book = self.parameters.book
            exemplary.acquisition_date = self.parameters.acquisition_date
            exemplary.acquisition_price = self.parameters.acquisition_price
            exemplary.identifier = self.parameters.identifier_start + str(
                len(to_create) + 1)
            exemplary.is_for_sale = self.parameters.is_for_sale
    
            to_create.append(exemplary)
        Exemplary.save(to_create)
        self.parameters.exemplaries = to_create
        return 'open_exemplaries'

    def do_open_exemplaries(self, action):
        action['pyson_domain'] = PYSONEncoder().encode([
                ('id', 'in', [x.id for x in self.parameters.exemplaries])])
        return action, {}


class CreateExemplariesParameters(ModelView):
    'Create Exemplaries Parameters'
    __name__ = 'library.book.create_exemplaries.parameters'

    book = fields.Many2One('library.book', 'Livre', readonly=True)
    number_of_exemplaries = fields.Integer('Nombre d\'exemplaires',
        required=True, domain=[('number_of_exemplaries', '>', 0)],
        help='Le nombre d\'exemplaires qui vont être crées')
    identifier_start = fields.Char('Début de l\'identifiant ', required=True,
        help='Les premiers chiffres de l\'identifiant à générer')
    acquisition_date = fields.Date(' Date d\'acquisition')
    acquisition_price = fields.Numeric('Prix d\'acquisition ', digits=(16, 2),
        domain=[('acquisition_price', '>=', 0)],
        help='Le prix d\'achat de l\'exemplaire')
    exemplaries = fields.Many2Many('library.book.exemplary', None, None,
        'Exemplaires')
    is_for_sale = fields.Boolean('Pour la vente')
   
class FuseBooks(Wizard):
    'Fuse books'
    __name__ = 'library.book.fuse'

    start_state = 'check_authors'

    check_authors = StateTransition()
    select_main = StateView('library.book.fuse.select_main',
        'library.fuse_select_main_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Preview', 'check_compatibility', 'tryton-go-next',
                default=True)])
    check_compatibility = StateTransition()
    preview = StateView('library.book.fuse.preview',
        'library.fuse_preview_view_form', [
            Button('Précédent', 'select_main', 'tryton-go-previous'),
            Button('Annuler', 'end', 'tryton-cancel'),
            Button('Fusionner', 'merge', 'tryton-go-next', default=True)])
    merge = StateTransition()
    refresh = StateTransition()

    @classmethod
    def __setup__(cls):
        super().__setup__()
      
      
    def transition_check_authors(self):
        if Transaction().context.get('active_model', '') != 'library.book':
            raise UserError('L\'action doit être déclenché à partir du modéle Livre ')
        Book = Pool().get('library.book')
        books = Book.browse(Transaction().context.get('active_ids'))
        if len({x.author for x in books}) != 1:
            raise UserError('Vous ne pouvez pas séléctionner des livres de plusieurs auteurs')
        return 'select_main'

    def default_select_main(self, name):
        if self.select_main._default_values:
            return self.select_main._default_values
        Book = Pool().get('library.book')
        books = Book.browse(Transaction().context.get('active_ids'))
        return {
            'selected_books': [x.id for x in books],
            'main_book': Transaction().context.get('active_id'),
            'number_of_exemplaries': sum(x.number_of_exemplaries for x in
                books),
            }

    def transition_check_compatibility(self):
        pool = Pool()
        Warning = pool.get('res.user.warning')
        web_pdb.set_trace(port=8251)
        values = self._get_merge_values()
        bad_matches = [k for k, v in values.items() if not v[1]]

        if bad_matches:
            
             warning_name = Warning.format('Alerte Matching',[self])
          
             if Warning.check(warning_name):
                 warning_message = 'Les champs suivants ne matchent pas très bien ensemble: {fields}'.format(fields=', '.join(bad_matches))
                 raise UserWarning(warning_name, warning_message)
       
                 
        return 'preview'
            


    def _get_merge_fields(self):
        return ['isbn', 'editor', 'genre', 'summary', 'description',
            'publishing_date', 'cover', 'page_count', 'edition_stopped',
            'author']

    def _get_merge_values(self):
        result = {}
        for fname in self._get_merge_fields():
            main_value = getattr(self.select_main.main_book, fname, None)
            for book in self.select_main.selected_books:
                book_value = getattr(book, fname, None)
                if book_value is None:
                    continue
                if main_value is None:
                    main_value = book_value
                    continue
                if main_value == book_value:
                    continue
                result[fname] = (main_value, False)
                break
            else:
                result[fname] = (main_value, True)
        return result

    def default_preview(self, name):
        book = {k: v for k, (v, _) in self._get_merge_values().items()}
        for fname in ['editor', 'author', 'genre']:
            book[fname] = book[fname].id if book[fname] else None
        book['title'] = self.select_main.main_book.title
        return {
            'final_book': [book],
            'number_of_exemplaries': self.select_main.number_of_exemplaries,
            }

    def transition_merge(self):
        pool = Pool()
        Book = pool.get('library.book')
        Exemplary = pool.get('library.book.exemplary')
        book = self.select_main.main_book
        for fname, (value, _) in self._get_merge_values().items():
            setattr(book, fname, value)
        book.save()
        other_books = [x for x in self.select_main.selected_books if x != book]
        Exemplary.write(sum([list(x.exemplaries) for x in other_books], []),
            {'book': book.id})
        Book.delete(other_books)
        return 'end'

    def end(self):
        return 'reload'


class FuseBooksSelectMain(ModelView):
    'Fuse Books Select Main'
    __name__ = 'library.book.fuse.select_main'

    main_book = fields.Many2One('library.book', 'Livre principal', required=True,
        domain=[('id', 'in', Eval('selected_books'))])
    selected_books = fields.Many2Many('library.book', None, None,
        'Livres Séléctionnés', readonly=True)
    number_of_exemplaries = fields.Integer('Nombre d\'exemplaires',
        readonly=True)


class FuseBooksPreview(ModelView):
    'Fuse Books Preview'
    __name__ = 'library.book.fuse.preview'

    final_book = fields.One2Many('library.book', None, 'Livre final',
        readonly=True)
    number_of_exemplaries = fields.Integer('Nombre d\' exemplaires',
        readonly=True)
    