# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9002

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AtencionAlCliente = Agent('AtencionAlCliente',
                       agn.AtencionAlCliente,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Buscar_Productos':
        return buscar_productos(req, content)
    elif accion == 'Comprar':
        return comprar(req, content)
    elif accion == 'Buscar_Productos_Usuario':
        return buscar_productos_usuario(req, content)
    elif accion == 'Devolver':
        return devolver(req,content)
    
    
def comprar(req, content):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    # datos historial compra
    historial_compras = Graph()
    try:
        historial_compras.parse('./data/historial_compras.owl')
    except Exception as e:
        logging.info('No historial_compras found, creating a new one')
    compra = agn['compra_' + str(mss_cnt)]    
    historial_compras.add((compra, RDF.type, agn.compra))
    # Graph message
    cl_graph = Graph()
    cl_graph.add((content, RDF.type, Literal('Empezar_Envio_Compra')))
    # codigo postal
    codigo_postal = req.value(subject=content, predicate=agn.codigo_postal)
    logging.info('codigo postal: ' + codigo_postal)
    cl_graph.add((content, agn.codigo_postal, codigo_postal))
    historial_compras.add((compra, agn.codigo_postal, codigo_postal))
    # direccion
    direccion = req.value(subject=content, predicate=agn.direccion)
    logging.info('direccion: ' + direccion)
    cl_graph.add((content, agn.direccion, direccion))
    historial_compras.add((compra, agn.direccion, direccion))
    # id usuario
    id = req.value(subject=content, predicate=agn.id_usuario)
    logging.info('id usuario: ' + id)
    cl_graph.add((content, agn.id_usuario, id))
    historial_compras.add((compra, agn.id_usuario, id))
    # tarjeta bancaria
    tarjeta_bancaria = req.value(subject=content, predicate=agn.tarjeta_bancaria)
    logging.info('tarjeta_bancaria: ' + tarjeta_bancaria)
    historial_compras.add((compra, agn.tarjeta_bancaria, tarjeta_bancaria))
    # productos
    for item in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=item, predicate=agn.nombre)
        precio = get_precioDB(nombre)
        logging.info(nombre)
        cl_graph.add((item, RDF.type, agn.product))
        historial_compras.add((compra, agn.product, Literal(nombre)))
        cl_graph.add((item, agn.nombre, Literal(nombre)))
        cl_graph.add((item, agn.precio, Literal(precio)))
    historial_compras.serialize('./data/historial_compras.owl')
    # Enviar mensaje
    centro_logistico = AtencionAlCliente.directory_search(DirectoryAgent, agn.CentroLogistico)
    message = build_message(
        cl_graph,
        perf=Literal('request'),
        sender=AtencionAlCliente.uri,
        receiver=centro_logistico.uri,
        msgcnt=mss_cnt,
        content=content
    )
    send_message(message, centro_logistico.address)    
    return Graph().serialize(format='xml')


def buscar_productos(req, content):    
    req_dict = {}
    if req.value(subject=content, predicate=agn['min_precio']):
        logging.info('Entra MIN precio')
        req_dict['min_precio'] = req.value(subject=content, predicate=agn['min_precio'])
        logging.info(req_dict['min_precio'])    
    if req.value(subject=content, predicate=agn['max_precio']):
        logging.info('Entra MAX precio')
        req_dict['max_precio'] = req.value(subject=content, predicate=agn['max_precio'])
        logging.info(req_dict['max_precio'])    
    return build_response(**req_dict)


def build_response(tieneMarca='(.*)', min_precio=0, max_precio=sys.float_info.max):
    productos = Graph()
    productos.parse('./data/product.owl')

    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tieneMarca
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?precio > $min_precio && 
                ?precio < $max_precio
            )
        }
    ''').substitute(dict(
        min_precio=min_precio,
        max_precio=max_precio
    ))

    result = productos.query(
        sparql_query,
        initNs=dict(
            foaf=FOAF,
            rdf=RDF,
            ns=agn,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )

    result_message = Graph()
    for x in result:
        result_message.add((x.producto, RDF.type, agn.product))
        result_message.add((x.producto, agn.nombre, x.nombre))
        result_message.add((x.producto, agn.peso, x.peso))
        result_message.add((x.producto, agn.precio, x.precio))
        result_message.add((x.producto, agn.tieneMarca, x.tieneMarca))

    return result_message.serialize(format='xml')

def get_precioDB(nombre):
    productos = Graph()
    productos.parse('./data/product.owl')

    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            FILTER (
                ?nombre = '$nombre' 
            )
        }
    ''').substitute(dict(
        nombre = nombre
    ))

    result = productos.query(
        sparql_query,
        initNs=dict(
            foaf=FOAF,
            rdf=RDF,
            ns=agn,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )
    for x in result:
        return x.precio


def buscar_productos_usuario(req, content):    
    req_dict = {}
    if req.value(subject=content, predicate=agn['id_usuario']):
        logging.info('Entra ID Usuario')
        req_dict['id_usuario'] = req.value(subject=content, predicate=agn['id_usuario'])
        logging.info(req_dict['id_usuario'])        
    return build_response_devolver(**req_dict)


def build_response_devolver(id_usuario=0):
    productos = Graph()
    productos.parse('./data/historial_compras.owl')
    logging.info("ID Usuario en la busqueda " + id_usuario) 

    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            ?compra ns:id ?id .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
    ''').substitute(dict(
        id_usuario = id_usuario
    ))

    result = productos.query(
        sparql_query,
        initNs=dict(
            foaf=FOAF,
            rdf=RDF,
            ns=agn,
            ns2=Namespace("http://ALIEXPLESS.ECSDI/")
        )
    )

    i = 0
    result_message = Graph()
    for x in result:
        producto = agn[x.product + '_' + i]
        result_message.add((producto, RDF.type, agn.product))
        result_message.add((producto, agn.nombre, x.product))
        result_message.add((producto, agn.id, x.id))
        i = i + 1

    return result_message.serialize(format='xml')

def devolver(req, content):
    logging.info('Empezamos devolucion')
    id_usuario = req.value(subject=content, predicate=agn.id_usuario)
    logging.info('ID Usuario devolucion = ' + str(id_usuario))
    motivo = req.value(subject=content, predicate=agn.motivo)
    logging.info('Motivo devolucion = ' + str(motivo))
    nombre = req.value(subject=content, predicate=agn.producto)
    logging.info('Nombre producto de devolucion = ' + str(nombre))
    id_compra = req.value(subject=content, predicate=agn.id_compra)
    logging.info('ID Compra de producto de devolucion = ' + str(id_compra))

    resultado = 'null'
    precio = 0

    if str(motivo) == 'equivocado':
        resultado = 'Devolucion por equivocacion'
        precio = get_precioDB(nombre)
    elif str(motivo) == 'defectuoso':
        prob_dev = random.randint(0, 100)
        if prob_dev < 90:
            resultado = 'Devolucion por producto defectuoso'
            precio = get_precioDB(nombre)
        else:
            resultado = 'Devolucion rechazada'
    elif str(motivo) == 'no_satisface':
        prob_dev = random.randint(0, 100)
        if prob_dev < 70:
            resultado = 'Devolucion por producto que no satisface las necesidades del comprador'
            precio = get_precioDB(nombre)
        else:
            resultado = 'Devolucion rechazada'


    result_message = Graph()

    respuesta = agn['respuesta' + str(mss_cnt)]
    result_message.add((respuesta, RDF.type, agn.respuesta))
    result_message.add((respuesta, agn.resultado, Literal(resultado)))

    if precio > Literal(0):
        logging.info("Entra delete")
        id_compra_elim = agn['compra_' + str(id_compra)]
        logging.info(id_compra_elim)
        productos = Graph()
        productos.parse('./data/historial_compras.owl')
        productos.remove((id_compra_elim, agn.product, Literal(nombre)))
        #mensaje a pagador

    return result_message.serialize(format='xml')


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
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AtencionAlCliente.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


