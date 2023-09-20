import datetime
import io
import os
from trytond.pool import Pool
from trytond.model import ModelView, fields
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, StateAction
from trytond.wizard import Button
from trytond.pyson import Date, Eval, PYSONEncoder
from trytond.exceptions import UserError
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


__all__ = [
    'Borrow',
    'BorrowSelectBooks',
    'Return',
    'ReturnSelectCheckouts',
    ]


class Borrow(Wizard):
    'Borrow books'
    __name__ = 'library.user.borrow'

    start_state = 'select_books'
    select_books = StateView('library.user.borrow.select_books',
        'library_transaction.borrow_select_books_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Emprunter', 'borrow', 'tryton-go-next', default=True)])
    borrow = StateTransition()
    checkouts = StateAction('library_transaction.act_open_user_checkout')

    @classmethod
    def __setup__(cls):
        super().__setup__()
    
    def default_select_books(self, name):
        user = None
        exemplaries = []
       
        if Transaction().context.get('active_model') == 'library.user':
            user = Transaction().context.get('active_id')
       
    
        elif Transaction().context.get('active_model') == 'library.book':
            books = Pool().get('library.book').browse(
                Transaction().context.get('active_ids'))
            for book in books:
                if not book.is_available_for_borrow:
                    continue
                for exemplary in book.exemplaries:
                    if exemplary.is_available_for_borrow:
                        break
        return {
            'user': user,
            'exemplaries': exemplaries,
            'date': datetime.date.today(),
            }

    def transition_borrow(self):
        Checkout = Pool().get('library.user.checkout')
        if not self.select_books.user.subscription :
          raise UserError('Une personne qui n\'a pas un abonnement ne peut pas emprunter de livres')
        elif  not self.select_books.user.subscription.status:
             raise UserError('Une personne dont son abonnement n\'est plus valable ne peut pas emprunter de livres')
        exemplaries = self.select_books.exemplaries
        user = self.select_books.user
        checkouts = []
        for exemplary in exemplaries:
            if not exemplary.is_available_for_borrow:
                raise UserError('L\'exemplaire n\'est pas disponible pour l\'emprunt', {
                        'exemplaire': exemplary.rec_name})
            checkouts.append(Checkout(
                    user=user, date=self.select_books.date,
                    exemplary=exemplary))
        Checkout.save(checkouts)
        self.select_books.checkouts = checkouts
        return 'checkouts'

    def do_checkouts(self, action):
        action['pyson_domain'] = PYSONEncoder().encode([
                ('id', 'in', [x.id for x in self.select_books.checkouts])])
        return action, {}


class BorrowSelectBooks(ModelView):
    'Select Books'
    __name__ = 'library.user.borrow.select_books'

    user = fields.Many2One('library.user', 'Client', required=True)
    exemplaries = fields.Many2Many('library.book.exemplary', None, None,
        'Exemplaires', required=True, domain=[('is_available_for_borrow', '=', True)])
    date = fields.Date('Date', required=True, domain=[('date', '<=', Date())])
    checkouts = fields.Many2Many('library.user.checkout', None, None,
        'Emprunts', readonly=True)


class Return(Wizard):
    'Return'
    __name__ = 'library.user.return'

    start_state = 'select_checkouts'
    select_checkouts = StateView('library.user.return.checkouts',
        'library_transaction.return_checkouts_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Retourner', 'return_', 'tryton-go-next', default=True)])
    return_ = StateTransition()

    @classmethod
    def __setup__(cls):
        super().__setup__()
    

    def default_select_checkouts(self, name):
        Checkout = Pool().get('library.user.checkout')
        user = None
        checkouts = []
        if Transaction().context.get('active_model') == 'library.user':
            user = Transaction().context.get('active_id')
            checkouts = [x for x in Checkout.search([
                        ('user', '=', user), ('return_date', '=', None)])]
        elif (Transaction().context.get('active_model') ==
                'library.user.checkout'):
            checkouts = Checkout.browse(
                Transaction().context.get('active_ids'))
            if len({x.user for x in checkouts}) != 1:
                raise UserError('On ne peut pas retourner des livres de plusieurs clients en même temps  ')
            if any(x.exemplary.is_available_for_borrow for x in checkouts):
                raise UserError('On ne peut pas retourner un livre disponible')
            user = checkouts[0].user.id
        return {
            'user': user,
            'checkouts': [x.id for x in checkouts],
            'date': datetime.date.today(),
            }

    def transition_return_(self):
        Checkout = Pool().get('library.user.checkout')
        Checkout.write(list(self.select_checkouts.checkouts), {
                'return_date': self.select_checkouts.date})
        return 'end'


class ReturnSelectCheckouts(ModelView):
    'Select Checkouts'
    __name__ = 'library.user.return.checkouts'

    user = fields.Many2One('library.user', 'User', required=True)
    checkouts = fields.Many2Many('library.user.checkout', None, None,
        'Emprunts', domain=[('user', '=', Eval('user')),
            ('return_date', '=', None)],   depends=['user'])
    date = fields.Date('Date', required=True, domain=[('date', '<=', Date())])


class CreateSubscription(Wizard):
    'Create Subscription'
    __name__ = 'library.user.create_subscription'

    start_state = 'parameters'
    parameters = StateView('library.user.create_subscription.parameters',
        'library_transaction.create_subscription_parameters_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Créer', 'create_subscription', 'tryton-go-next',
                default=True)])
    create_subscription = StateTransition()
    open_subscription = StateAction('library_transaction.act_open_user_subscription')
    created_subscription_id = None


    @classmethod
    def __setup__(cls):
        super().__setup__()
       
    def default_parameters(self, name):
        if Transaction().context.get('active_model', '') != 'library.user':
            raise UserError('Cette action doit être déclenché du model client')
        return {
            'start_date': datetime.date.today(),
            'user': Transaction().context.get('active_id'),
            'subscription_type':'mensuel'
            }

    def transition_create_subscription(self):
        if self.parameters.user.subscription !=None:
            raise UserError('Chaque client ne peut avoir qu\'un seul abonnement')
      
        Subscription = Pool().get('library.user.subscription')
        subscription = Subscription()
        subscription.user = self.parameters.user
        subscription.start_date = self.parameters.start_date
        subscription.subscription_type = self.parameters.subscription_type
        subscription.save()
        self.created_subscription_id = subscription.id

        return 'open_subscription'

    """
    def do_open_subscription(self, action):
    

  

     return {
        'name': 'Créer Abonnement',
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'library.user.subscription',
        'res_id':  self.created_subscription_id ,
        'views': [(False, 'form')],
        'type': 'ir.actions.act_window',
        'target': 'current',
        'context': {
            'form_view_ref': 'library_transaction.act_open_user_subscription_view_form',
        },
    }
    """
    def do_open_subscription(self, action):
        
        if action and isinstance(action, list) and len(action) > 0:
            action = action[0]
            action.setdefault('name', 'Créer Abonnement')
            action.setdefault('view_type', 'form')
            action.setdefault('view_mode', 'form')
            action.setdefault('res_model', 'library.user.subscription')
            action.setdefault('res_id', self.created_subscription_id)
            action.setdefault('views', [(True, 'form')])
            action.setdefault('type', 'ir.actions.act_window')
            action.setdefault('target', 'current')
            action.setdefault('context', {
            'form_view_ref': 'library_transaction.act_open_user_subscription_view_form',
        })

        return action, {}
     
     




    

class CreateSubscriptionParameters(ModelView):
      'Create Subscription Parameters'
      __name__ = 'library.user.create_subscription.parameters'

      user = fields.Many2One('library.user', 'Client', readonly=True)
      subscription_type = fields.Selection([('annuel', 'Annuel'), ('mensuel', 'Mensuel'),('trimestriel','Trimestriel'),('semestriel','Semestriel')], 'Type d\'abonnement',
        required=True
        )
      start_date = fields.Date('Date de début de l\'abonnement ', required=True)

class RenewSubscription(Wizard):
      'Renew Subscription '
      __name__ = 'library.user.renew_subscription'
     
      start_state =  'renew_subscription'
      renew_subscription = StateAction('library_transaction.act_open_user_subscription')
       
       
       
      def  do_renew_subscription(self, action):
        
        if action and isinstance(action, list) and len(action) > 0:
            action = action[0]
            action.setdefault('name', 'Renouveler Abonnement')
            action.setdefault('view_type', 'form')
            action.setdefault('view_mode', 'form')
            action.setdefault('res_model', 'library.user.subscription')
            action.setdefault('res_id', Transaction().context.get('active_id').subscription.id)
            action.setdefault('views', [(True, 'form')])
            action.setdefault('type', 'ir.actions.act_window')
            action.setdefault('target', 'current')
        

        return action, {}
      
class GenerateInvoice(Wizard):
    'Generate Invoice PDF'
    __name__ = 'library.user.invoice.generate_invoice_pdf'

    start_state = 'generate_invoice_pdf'
       
    generate_invoice_pdf = StateAction('library_transaction.act_generate_invoice_pdf') 

  
    # def do_generate_invoice_pdf(self,action):
    #     if Transaction().context.get('active_model') == 'library.user.invoice':
    #         invoice_id = Transaction().context.get('active_id')
    #         Invoice = Pool().get('library.user.invoice')

    #         invoices = Invoice.search([('id', '=', invoice_id)])
    #         if invoices:
    #             invoice = invoices[0]
    

    #             filename = 'facture_{}.pdf'.format(invoice.id)
    #             folder_path = 'invoices'
    #             if not os.path.exists(folder_path):
    #              os.makedirs(folder_path)
    #             file_path = os.path.join(folder_path, filename) 
    #             c = canvas.Canvas(file_path, pagesize=letter)
 

  
    #             c.setFont("Helvetica", 12)
    #             c.drawString(1 * inch, 10 * inch, "Numéro de la facture: {}".format(invoice.id))
    #             c.drawString(1 * inch, 9.5 * inch, "Date de la facture: {}".format(invoice.invoice_date))
    #             c.drawString(1 * inch, 9 * inch, "Client: {}".format(invoice.user.name))

    #             line_height = 8.5 * inch
    #             for line in invoice.invoice_lines:
    #              line_height -= 0.3 * inch
    #              c.drawString(1 * inch, line_height, "Book: {}".format(line.book.title))
    #              c.drawString(2 * inch, line_height - 0.2 * inch, "Quantité: {}".format(line.number_of_exemplaries_to_sell))
    #              c.drawString(3 * inch, line_height - 0.4 * inch, "Prix (HT): {}".format(line.sale_price_HT))
    #              c.drawString(4 * inch, line_height - 0.6 * inch, "Prix (HT après remise): {}".format(line.sale_price_HT_after_discount))
    #              c.drawString(5 * inch, line_height - 0.8 * inch, "Prix (TTC): {}".format(line.sale_price_TTC))

    #             c.line(1 * inch, 1 * inch, 7.5 * inch, 1 * inch)
    #             c.showPage()
    #             c.save()
    
    # def do_generate_invoice_pdf(self, action):
      
    #   if Transaction().context.get('active_model') == 'library.user.invoice':
    #     invoice_id = Transaction().context.get('active_id')
    #     Invoice = Pool().get('library.user.invoice')

    #     invoices = Invoice.search([('id', '=', invoice_id)])
    #     if invoices:
    #         invoice = invoices[0]

    #     filename = 'facture_{}.pdf'.format(invoice.id)
    #     folder_path = 'invoices'
    #     if not os.path.exists(folder_path):
    #         os.makedirs(folder_path)
    #     file_path = os.path.join(folder_path, filename)
    #     c = canvas.Canvas(file_path, pagesize=letter)

    #     # En-tête avec numéro de facture
    #     header_color = (0.2, 0.4, 0.8)  # Couleur bleue pour l'en-tête
    #     c.setFillColor(header_color)
    #     c.rect(0, 770, 612, 300, fill=True)  # Increased height to 50
    #     c.setFillColorRGB(1, 1, 1) 
    #     c.drawCentredString(306, 780, "Numéro de la facture: {}".format(invoice.id))  # Increased y-coordinate to 790
    #     c.drawCentredString(306, 760, "Client: {}".format(invoice.user.name))  # Increased y-coordinate to 770
    #     c.drawCentredString(306, 740, "Date de la facture: {}".format(invoice.invoice_date))  # Increased y-coordinate to 750
    
     
    #     # c.drawCentredString(306, 780, "Numéro de la facture: {}".format(invoice.id))
    #     # c.drawCentredString(306, 760, "Client: {}".format(invoice.user.name))
    #     # c.drawCentredString(306, 740, "Date de la facture: {}".format(invoice.invoice_date))

    #     # Tableau des lignes de facture
    #     table_header_color = (0.7, 0.7, 0.7)  # Couleur gris clair pour l'en-tête du tableau
    #     c.setFillColor(table_header_color)
    #     c.rect(50, 700, 512, 30, fill=True)
    #     c.setFillColorRGB(0, 0, 0)  # Couleur noire pour le texte
    #     c.setFont("Helvetica-Bold", 12)

    #     # Noms des colonnes
    #     c.drawCentredString(100, 710, "Livre")
    #     c.drawCentredString(200, 710, "Quantité")
    #     c.drawCentredString(300, 710, "Prix (HT)")
    #     c.drawCentredString(400, 710, "Prix (HT après remise)")
    #     c.drawCentredString(500, 710, "Prix (TTC)")

    #     # Lignes de facture
    #     line_height = 670
    #     for line in invoice.invoice_lines:
    #         line_height -= 25  # Hauteur de la ligne du tableau
    #         c.drawString(60, line_height, line.book.title)
    #         c.drawCentredString(200, line_height, str(line.number_of_exemplaries_to_sell))
    #         c.drawCentredString(300, line_height, str(line.sale_price_HT))
    #         c.drawCentredString(400, line_height, str(line.sale_price_HT_after_discount))
    #         c.drawCentredString(500, line_height, str(line.sale_price_TTC))
    #     # Lignes pour les totaux
    #     line_height -= 50
    #     c.drawString(60, line_height, "Total HT:")
    #     c.drawCentredString(300, line_height, str(invoice.total_sale_price_HT))
    #     c.drawString(60, line_height - 25, "Total HT après remise:")
    #     c.drawCentredString(400, line_height - 25, str(invoice.total_HT_after_discount))
    #     c.drawString(60, line_height - 50, "Total TTC:")
    #     c.drawCentredString(500, line_height - 50, str(invoice.total_sale_price_TTC))    

    #     c.showPage()
    #     c.save()
    # def do_generate_invoice_pdf(self, action):
    #  if Transaction().context.get('active_model') == 'library.user.invoice':
    #     invoice_id = Transaction().context.get('active_id')
    #     Invoice = Pool().get('library.user.invoice')

    #     invoices = Invoice.search([('id', '=', invoice_id)])
    #     if invoices:
    #         invoice = invoices[0]

    #     filename = 'facture_{}.pdf'.format(invoice.id)
    #     folder_path = 'invoices'
    #     if not os.path.exists(folder_path):
    #         os.makedirs(folder_path)
    #     file_path = os.path.join(folder_path, filename)
    #     c = canvas.Canvas(file_path, pagesize=letter)

    #     # En-tête avec numéro de facture
    #     header_color = (0.2, 0.4, 0.8)  # Couleur bleue pour l'en-tête
    #     c.setFillColor(header_color)
    #     c.rect(0, 750, 612, 110, fill=True)  # Augmentation de la hauteur à 40 pour l'en-tête
    #     c.setFillColorRGB(1, 1, 1) 
    #     c.setFont("Helvetica-Bold", 14)
    #     c.drawCentredString(306, 775, "Numéro de la facture: {}".format(invoice.id))  # Déplacement vers le haut
    #     c.drawCentredString(306, 755, "Client: {}".format(invoice.user.name))  # Déplacement vers le haut
    #     c.drawCentredString(306, 735, "Date de la facture: {}".format(invoice.invoice_date))  # Déplacement vers le haut

    #     # Tableau des lignes de facture
    #     table_header_color = (0.7, 0.7, 0.7)  # Couleur gris clair pour l'en-tête du tableau
    #     c.setFillColor(table_header_color)
    #     c.rect(50, 700, 512, 30, fill=True)
    #     c.setFillColorRGB(0, 0, 0)  # Couleur noire pour le texte
    #     c.setFont("Helvetica-Bold", 12)

    #     # Noms des colonnes
    #     c.drawCentredString(100, 710, "Livre")
    #     c.drawCentredString(200, 710, "Quantité")
    #     c.drawCentredString(300, 710, "Prix (HT)")
    #     c.drawCentredString(400, 710, "Prix (HT après remise)")
    #     c.drawCentredString(500, 710, "Prix (TTC)")

    #     # Lignes de facture
    #     line_height = 670
    #     for line in invoice.invoice_lines:
    #         line_height -= 25  # Hauteur de la ligne du tableau
    #         c.drawString(60, line_height, line.book.title)
    #         c.drawCentredString(200, line_height, str(line.number_of_exemplaries_to_sell))
    #         c.drawCentredString(300, line_height, str(line.sale_price_HT))
    #         c.drawCentredString(400, line_height, str(line.sale_price_HT_after_discount))
    #         c.drawCentredString(500, line_height, str(line.sale_price_TTC))
            
    #     # Lignes pour les totaux
    #     line_height -= 50
    #     c.drawString(60, line_height, "Total HT:")
    #     c.drawCentredString(300, line_height, str(invoice.total_sale_price_HT))
    #     c.drawString(60, line_height - 25, "Total HT après remise:")
    #     c.drawCentredString(400, line_height - 25, str(invoice.total_HT_after_discount))
    #     c.drawString(60, line_height - 50, "Total TTC:")
    #     c.drawCentredString(500, line_height - 50, str(invoice.total_sale_price_TTC))    

    #     c.showPage()
    #     c.save()
    def do_generate_invoice_pdf(self, action):
     if Transaction().context.get('active_model') == 'library.user.invoice':
        invoice_id = Transaction().context.get('active_id')
        Invoice = Pool().get('library.user.invoice')

        invoices = Invoice.search([('id', '=', invoice_id)])
        if invoices:
            invoice = invoices[0]

        filename = 'facture_{}.pdf'.format(invoice.id)
        folder_path = 'invoices'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        file_path = os.path.join(folder_path, filename)
        c = canvas.Canvas(file_path, pagesize=letter)

        # En-tête avec numéro de facture
        #header_color = (0.2, 0.4, 0.8)  # Couleur bleue pour l'en-tête
        #c.setFillColor(header_color)
        #c.rect(0, 770, 612, 200, fill=True)  # Augmentation de la hauteur à 140 pour l'en-tête
        #c.setFillColorRGB(1, 1, 1) 
        #c.setFont("Helvetica-Bold", 14)
        c.setFillColor((255, 0 ,0)) 
        c.drawString(50, 770, "Numéro de la facture:")
        c.drawString(50, 750, "Client:")
        c.drawString(50, 730, "Date de la facture:")
        line_height = 710
        c.drawString(50, line_height, "Total HT:")
        c.drawString(50, line_height - 25, "Total HT après remise:")
        c.drawString(50, line_height - 50, "Total TTC:")
        c.setFillColor((0, 0 ,0)) 
        c.drawString(190, 770, str(invoice.id))
        c.drawString(110, 750, str(invoice.user.name))   
        c.drawString(172, 730, str(invoice.invoice_date))
        c.drawString(120, line_height, str(invoice.total_sale_price_HT)+" TND")
    
        c.drawString(195, line_height - 25, str(invoice.total_HT_after_discount)+" TND")
  
        c.drawString(130, line_height - 50, str(invoice.total_sale_price_TTC)+" TND") 
      



        table_header_color = (0.2, 0.4, 0.8)  # Couleur gris clair pour l'en-tête du tableau
        c.setFillColor(table_header_color)
        c.rect(50, 600, 512, 30, fill=True)  # Ajustement de la position du tableau vers le bas
         # Couleur noire pour le texte
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor((1,1,1))
        # Noms des colonnes
        c.drawCentredString(100, 610, "Livre")  # Ajustement de la position du nom des colonnes
        c.drawCentredString(200, 610, "Quantité")  # Ajustement de la position du nom des colonnes
        c.drawCentredString(300, 610, "Prix (HT)")  # Ajustement de la position du nom des colonnes
        c.drawCentredString(400, 610, "Prix (HT après remise)")  # Ajustement de la position du nom des colonnes
        c.drawCentredString(500, 610, "Prix (TTC)")  # Ajustement de la position du nom des colonnes
        c.setFillColor((0,0,0))
        # Lignes de facture
        line_height = 590
        for line in invoice.invoice_lines:
            line_height -= 25  # Hauteur de la ligne du tableau
            c.drawString(60, line_height, line.book.title)
            c.drawCentredString(200, line_height, str(line.number_of_exemplaries_to_sell))
            c.drawCentredString(300, line_height, str(line.sale_price_HT))
            c.drawCentredString(400, line_height, str(line.sale_price_HT_after_discount))
            c.drawCentredString(500, line_height, str(line.sale_price_TTC))
            
        # Lignes pour les totaux
   
        c.showPage()
        c.save()



            

                     


# class GenerateInvoice(Wizard):
#     'Generate Wizard'
#     __name__ = 'library.invoice.generate_invoice_pdf'

#     start_state = 'generate_invoice_pdf'
#     generate_invoice_pdf = StateTransition()
#     pdf = StateView('library.user.invoice_pdf',
#         'library_transaction.generate_invoice_pdf_view_form', [
#             Button('Cancel', 'end', 'tryton-cancel'),
#             Button('OK', 'invoices', 'tryton-go-next', default=True)])
#     invoices = StateAction('library_transaction.act_open_invoice')



# #     def transition_generate_invoice_pdf(self):
# #         if Transaction().context.get('active_model') == 'library.user.invoice':
# #             invoice_id = Transaction().context.get('active_id')
# #             Invoice = Pool().get('library.user.invoice')

# #             invoices = Invoice.search([('id', '=', invoice_id)])
# #             if invoices:
# #                 invoice = invoices[0]
    

# #             filename = 'facture_{}.pdf'.format(invoice.id)
# #             pdf_buffer = io.BytesIO()
# #             c = canvas.Canvas(pdf_buffer, pagesize=letter)
  
# #             c.setFont("Helvetica", 12)
# #             c.drawString(1 * inch, 10 * inch, "Numéro de la facture: {}".format(invoice.id))
# #             c.drawString(1 * inch, 9.5 * inch, "Date de la facture: {}".format(invoice.invoice_date))
# #             c.drawString(1 * inch, 9 * inch, "Client: {}".format(invoice.user.name))

# #             line_height = 8.5 * inch
# #             for line in invoice.invoice_lines:
# #                 line_height -= 0.3 * inch
# #                 c.drawString(1 * inch, line_height, "Book: {}".format(line.book.title))
# #                 c.drawString(2 * inch, line_height - 0.2 * inch, "Quantité: {}".format(line.number_of_exemplaries_to_sell))
# #                 c.drawString(3 * inch, line_height - 0.4 * inch, "Prix (HT): {}".format(line.sale_price_HT))
# #                 c.drawString(4 * inch, line_height - 0.6 * inch, "Prix (HT après remise): {}".format(line.sale_price_HT_after_discount))
# #                 c.drawString(5 * inch, line_height - 0.8 * inch, "Prix (TTC): {}".format(line.sale_price_TTC))

# #             c.line(1 * inch, 1 * inch, 7.5 * inch, 1 * inch)
# #             c.save()

# #             pdf_buffer.seek(0)

# #             # Sauvegarder le contenu du fichier PDF généré dans le champ binaire pdf_content
# #             self.pdf.pdf_content = pdf_buffer.getvalue()
# #             return 'pdf'
 
#     def transition_generate_invoice_pdf(self):
    

#          if Transaction().context.get('active_model') == 'library.user.invoice':
#             invoice_id = Transaction().context.get('active_id')
#             Invoice = Pool().get('library.user.invoice')

#             invoices = Invoice.search([('id', '=', invoice_id)])
#             if invoices:
#                 invoice =invoices[0]
#             filename = 'facture_{}.pdf'.format(invoice.id)
#             c = canvas.Canvas(filename, pagesize=letter)
  
#             c.setFont("Helvetica", 12)
#             c.drawString(1 * inch, 10 * inch, "Numéro de la facture: {}".format(invoice.id))
#             c.drawString(1 * inch, 9.5 * inch, "Date de la facture: {}".format(invoice.invoice_date))
#             c.drawString(1 * inch, 9 * inch, "Client: {}".format(invoice.user.name))

#             line_height = 8.5 * inch
#             for line in invoice.invoice_lines:
#              line_height -= 0.3 * inch
#              c.drawString(1 * inch, line_height, "Book: {}".format(line.book.title))
#              c.drawString(2 * inch, line_height - 0.2 * inch, "Quantité: {}".format(line.number_of_exemplaries_to_sell))
#              c.drawString(3 * inch, line_height - 0.4 * inch, "Prix (HT): {}".format(line.sale_price_HT))
#              c.drawString(4 * inch, line_height - 0.6 * inch, "Prix (HT aprés remise): {}".format(line.sale_price_HT_after_discount))
#              c.drawString(5 * inch, line_height - 0.8 * inch, "Prix (TTC): {}".format(line.sale_price_TTC))

        
#             c.line(1 * inch, 1 * inch, 7.5 * inch, 1 * inch)
#             c.showPage()
#             c.save()
#             self.pdf.pdf_content = c.getpdfdata()

#             return 'pdf'
         
#     def do_invoices(self, action):
        
#         if action and isinstance(action, list) and len(action) > 0:
#             action = action[0]
#             action.setdefault('name', 'Générer facture PDF')
#             action.setdefault('view_type', 'tree')
#             action.setdefault('view_mode', 'tree')
#             action.setdefault('res_model', 'library.user.invoice') 
#             action.setdefault('views', [(True, 'tree')])
#             action.setdefault('type', 'ir.actions.act_window')
#             action.setdefault('target', 'current')
        

#         return action, {}
# class InvoicePDF(ModelView):
#     'Invoice PDF'
#     __name__ = 'library.user.invoice_pdf'
 
#     pdf_content = fields.Binary('Facture PDF générée', readonly=True)


    
       
