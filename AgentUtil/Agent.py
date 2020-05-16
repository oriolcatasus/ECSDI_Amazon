"""
.. module:: Agent

Agent
******

:Description: Agent
  Clase para guardar los atributos de un agente

"""
from rdflib.namespace import FOAF, RDF
from AgentUtil.OntoNamespaces import ACL, DSO
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from rdflib import Graph, Literal, Namespace
from Constants.Constants import ONTOLOGY

agn = Namespace(ONTOLOGY)
mss_cnt = 0

from AgentUtil.Logging import config_logger
logging = config_logger(level=1)


class Agent():
  def __init__(self, name, uri, address, stop):
    self.name = name
    self.uri = uri
    self.address = address
    self.stop = stop

  def register_agent(self, DirectoryAgent):
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logging.info('Nos registramos')

    global mss_cnt

    gmess = Graph()

    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[self.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, self.uri))
    gmess.add((reg_obj, FOAF.name, Literal(self.name)))
    gmess.add((reg_obj, DSO.Address, Literal(self.address)))
    gmess.add((reg_obj, DSO.AgentType, self.uri))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=self.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

  def directory_search(self, DirectoryAgent, type):
    global mss_cnt
    logging.info('Buscamos en el servicio de registro')

    gmess = Graph()

    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[self.name + '-search']
    gmess.add((reg_obj, RDF.type, DSO.Search))
    gmess.add((reg_obj, DSO.AgentType, type))

    msg = build_message(gmess, perf=ACL.request,
                        sender=self.uri,
                        receiver=DirectoryAgent.uri,
                        content=reg_obj,
                        msgcnt=mss_cnt)
    gr = send_message(msg, DirectoryAgent.address)
    mss_cnt += 1
    logging.info('Recibimos informacion del agente')
    
    content = get_message_properties(gr)['content']
    address = gr.value(subject=content, predicate=DSO.Address)
    logging.info('address:')
    logging.info(address)
    uri = gr.value(subject=content, predicate=DSO.Uri)
    logging.info('uri:')
    logging.info(uri)
    name = gr.value(subject=content, predicate=FOAF.name)
    logging.info('Name:')
    logging.info(name)
    return Agent(name, uri, address, None)