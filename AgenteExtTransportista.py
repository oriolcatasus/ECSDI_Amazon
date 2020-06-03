# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import random
import uuid
import datetime
import argparse

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.OntoNamespaces import ACL
import requests
import logging
logging.basicConfig(level=logging.DEBUG)
import Constants.Constants as Constants

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
hostname = '127.0.1.1'
if args.port is None:
    port = random.randint(9101, 9999)
else:
    port = args.port

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

ofertas_ini = {}
ofertas = {}

# Datos del Agente

AgenteExtTransportista = Agent('Transportista_' + str(port),
                       agn.Transportista,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
TransportistaDirAgent = Agent('TransportistaDirAgent',
                       agn.Directory,
                       'http://%s:9100/Register' % hostname,
                       'http://%s:9100/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Negociar':        
        return negociar(req, content)
    elif accion == 'Contraoferta':
        return contraoferta(req, content)
    elif accion == 'Transportar':
        return transportar(req, content)

def negociar(req, content):
    global mss_cnt
    global ofertas
    global ofertas_ini

    mss_cnt = mss_cnt + 1
    logging.info('Peticion de oferta')
    id_peticion = int(req.value(content, agn.id_peticion))
    logging.info('id petición: ' + str(id_peticion))
    prioridad_envio = int(req.value(content, agn.prioridad_envio))
    total_peso = float(req.value(content, agn.total_peso))
    logging.info('Peso de la petición: ' + str(total_peso))
    if (prioridad_envio == 1):
        logging.info('Envio en 1 dia')
    else:
        logging.info('Envio sin prioridad')
    precio_base = int(random.uniform(5, 9))
    logging.info('Precio base: ' + str(precio_base))
    precio_extra_peso = int(random.uniform(0.05, 0.09) * total_peso)
    logging.info('Precio extra por peso: ' + str(precio_extra_peso))
    precio_extra_prioridad = prioridad_envio * int(random.uniform(5, 9))
    logging.info('Precio extra por prioridad: ' + str(precio_extra_prioridad))
    ofertas[id_peticion] = ofertas_ini[id_peticion] = precio_base + precio_extra_peso + precio_extra_prioridad
    logging.info('Precio total oferta: ' + str(ofertas[id_peticion]))
    graph = Graph()
    oferta = agn['oferta_' + str(mss_cnt)]
    graph.add((oferta, RDF.type, Literal('Oferta_Transportista')))
    graph.add((oferta, agn.oferta, Literal(ofertas_ini[id_peticion])))
    return graph.serialize(format='xml')

def contraoferta(req, content):
    global mss_cnt
    global ofertas
    global ofertas_ini

    mss_cnt = mss_cnt + 1
    id_peticion = int(req.value(content, agn.id_peticion))
    logging.info('id petición: ' + str(id_peticion))
    contraoferta = int(req.value(content, agn.contraoferta))
    logging.info('Contraoferta: ' + str(contraoferta))
    logging.info('Nuestra oferta inicial: ' + str(ofertas_ini[id_peticion]))
    # Incremento de mi oferta inicial respecto la contraoferta (factor entre 0 y 1)
    incr = contraoferta/ofertas_ini[id_peticion]
    p = random.uniform(0, 1)
    # La posibilidad de aceptar una contraoferta sera random
    # pero será mayor cuanto más cerca de nuestra oferta inicial esté la contraoferta
    p_aceptar = incr*p
    logging.info('p_aceptar: ' + str(p_aceptar))
    estado_negociacion = ''
    if p_aceptar > 0.5:
        logging.info('Aceptamos la contraoferta')
        ofertas[id_peticion] = contraoferta
        estado_negociacion = 'Continuar'
    elif p_aceptar > 0.2:
        logging.info('Rechazamos la contraoferta')
        logging.info('Proponemos una nueva oferta')
        # La nueva contraoferta será random
        # pero será menor cuanto más cerca de nuestra oferta inicial esté la contraoferta
        diff = ofertas[id_peticion] - contraoferta
        ofertas[id_peticion] -= int(diff * (p_aceptar + random.uniform(0, 0.4)))
        logging.info('Nueva contraoferta: ' + str(ofertas[id_peticion]))
        estado_negociacion = 'Continuar'
    else:
        logging.info('Rechazamos la contraoferta')
        logging.info('NO proponemos una nueva oferta')
        estado_negociacion = 'Rechazar'
    graph = Graph()
    oferta = agn['contraoferta_transportista' + str(mss_cnt)]
    graph.add((oferta, RDF.type, Literal('Contraoferta_Transportista')))   
    graph.add((oferta, agn.contraoferta, Literal(ofertas[id_peticion])))
    graph.add((oferta, agn.negociacion, Literal(estado_negociacion)))
    return graph.serialize(format='xml')

def transportar(req, content):
    global mss_cnt
    global ofertas

    mss_cnt = mss_cnt + 1
    logging.info('Transporte recibido:')
    id_peticion = int(req.value(content, agn.id_peticion))
    prioridad_envio = int(req.value(content, agn.prioridad_envio))
    total_peso = float(req.value(content, agn.total_peso))
    fecha_recepcion = None
    if (prioridad_envio == 1):
        logging.info('Envío en 1 día')
        fecha_recepcion = datetime.date.today() + datetime.timedelta(days=1)
    else:
        logging.info('Envío sin prioridad')
        extra_days = int(random.uniform(7, 30))
        fecha_recepcion = datetime.date.today() + datetime.timedelta(days=extra_days)
    for item in req.subjects(RDF.type, agn.compra):
        lote = req.value(subject=item, predicate=agn.lote)
        logging.info('Lote: ' + lote)
        direccion = req.value(subject=item, predicate=agn.direccion)
        logging.info('Dirección: ' + direccion)
        codigo_postal = req.value(subject=item, predicate=agn.codigo_postal)
        logging.info('Codigo postal: ' + codigo_postal)
    logging.info('Precio envio: ' + str(ofertas[id_peticion]))
    logging.info('Fecha de recepción del envio: ' + str(fecha_recepcion))
    logging.info('Peso del envio: ' + str(total_peso))
    graph = Graph()
    sujeto = agn['respuesta']
    graph.add((sujeto, agn.precio, Literal(ofertas[id_peticion])))
    graph.add((sujeto, agn.fecha_recepcion, Literal(fecha_recepcion)))
    return graph.serialize(format='xml')


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    AgenteExtTransportista.unregister_agent(TransportistaDirAgent)


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AgenteExtTransportista.register_agent(TransportistaDirAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    tidyup()
    print('The End')
